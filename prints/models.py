import json
import re

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property

from stripe_subscription.stripe_api import stripe

from shopified_core.utils import app_link


class Category(models.Model):
    class Meta:
        verbose_name_plural = 'Categories'

    source_type = models.CharField(max_length=50, default='layerapp', choices=(('layerapp', 'LayerApp'),))
    source_id = models.IntegerField()
    title = models.CharField(max_length=255, default='')

    def __str__(self):
        return self.title


class ProductManager(models.Manager):
    def active(self):
        return super().get_queryset().filter(~models.Q(price_range=''))


class Product(models.Model):
    class Meta:
        ordering = 'title',

    objects = ProductManager()

    title = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='')
    product_type = models.ForeignKey(Category, null=True, on_delete=models.CASCADE)
    default_image = models.CharField(max_length=512, blank=True, default='')
    dropified_image = models.CharField(max_length=512, blank=True, default='', verbose_name="Default Image (Overrite)")

    source_type = models.CharField(max_length=50, default='layerapp', choices=(('layerapp', 'LayerApp'),))
    source_id = models.IntegerField(default=0, editable=False)
    source_data = models.TextField(default='{}')

    # For quick search of sizes and ships_from skus (separated by comma)
    skus = models.TextField(default='')
    price_range = models.CharField(max_length=50, default='', editable=False)

    def __str__(self):
        return f'{self.title} - Dropified:{self.id} - {self.get_source_type_display()}:{self.source_id}'

    def get_source_data_dict(self):
        try:
            return json.loads(self.source_data)
        except:
            return {}

    @property
    def is_layerapp(self):
        return self.source_type == 'layerapp'

    @cached_property
    def data(self):
        source_data = self.get_source_data_dict()
        if 'original_data' in source_data:
            del source_data['original_data']
        return source_data

    @cached_property
    def original_data(self):
        source_data = self.get_source_data_dict()
        return source_data.get('original_data', {})

    @cached_property
    def user_costs(self):
        try:
            prices = self.prices.all()
            prices_map = {}

            for price in prices:
                if not price.target:
                    continue

                prices_map[price.sku] = dict(
                    raw_cost=price.target,
                    cost=f'US ${price.target}',
                    suggested_price=price.retail and f'US ${price.retail}' or '-',
                )

            return prices_map
        except:
            return {}

    @cached_property
    def variants(self):
        get_source_variants = getattr(self, f'get_{self.source_type}_variants')
        return get_source_variants()

    @cached_property
    def images(self):
        get_source_images = getattr(self, f'get_{self.source_type}_images')
        return get_source_images()

    def get_price_range(self):
        prices = ' - '.join(self.price_range.split(','))
        return f'US ${prices}'

    def get_layerapp_variants(self):
        paired = self.data.get('paired')
        artwork_width = self.data.get('artwork_width')
        artwork_height = self.data.get('artwork_height')

        variants = self.data.get('variants', [])
        for variant in variants:
            variant['is_paired'] = paired == '1'
            variant['artwork_width'] = artwork_width
            variant['artwork_height'] = artwork_height

        return {
            'styles': variants,
            'sizes': list(self.data.get('sizes', {}).values())
        }

    def get_layerapp_images(self):
        # images = [{'src': self.default_image}]  # TODO: Wait for default without logo
        images = []
        for variant in self.data.get('variants', []):
            images.append({
                'src': variant.get('variant_image'),
            })
        return images

    def get_price_by_sku(self, sku):
        try:
            price = self.prices.get(sku=sku)

        except ProductPrice.DoesNotExist:
            raise Exception('Variant not available')

        # Without these prices we can't pay LayerApp or charge our customer
        assert price.target, f'No price found for this item ({sku})'
        assert price.source_profit, f'No price found for this item ({sku})'
        source_price = price.target + price.source_profit
        assert source_price, f'Item not available for ordering ({sku})'

        return {
            'dropified': price.target,
            'source': source_price,
            'dropified_profit': price.dropified_profit,
            'source_profit': price.source_profit,
        }
    get_price_by_sku.do_not_call_in_templates = True

    def get_country_by_sku(self, sku):
        data = self.original_data
        if sku == data.get('china_sku'):
            return 'China'
        if sku == data.get('usa_sku'):
            return 'United States'

        # Sizes can have custom SKU
        for size in data.get('sizes', []):
            if sku == size.get('china_sku'):
                return 'China'
            if sku == size.get('usa_sku'):
                return 'United States'

        return ''


class ProductPrice(models.Model):
    product = models.ForeignKey(Product, null=True, related_name='prices', on_delete=models.CASCADE)
    sku = models.CharField(max_length=100, unique=True, null=True, blank=True)
    dropified_profit = models.DecimalField(decimal_places=2, max_digits=9, verbose_name="Dropified Profit")
    source_profit = models.DecimalField(decimal_places=2, max_digits=9, verbose_name="LayerApp Profit")

    # Total price our users pay for summed with LayerApp and Dropified profits
    target = models.DecimalField(decimal_places=2, max_digits=9, verbose_name="User Price")
    # Suggested retail price
    retail = models.DecimalField(decimal_places=2, max_digits=9, blank=True, null=True, verbose_name="Retail Price (MSRP)")
    # The actual cost LayerApp pays for this item
    cost = models.DecimalField(decimal_places=2, max_digits=9, verbose_name="Product Cost")

    def __str__(self):
        return self.sku


class CustomProduct(models.Model):
    class Meta:
        ordering = 'title',

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.TextField(blank=True, default='')
    description = models.TextField(blank=True, default='')
    product_type = models.CharField(max_length=255, blank=True, default='')
    tags = models.TextField(blank=True, default='')
    vendor = models.CharField(max_length=255, default='', blank=True)
    price = models.DecimalField(decimal_places=2, max_digits=9, null=True, blank=True)
    compare_at = models.DecimalField(decimal_places=2, max_digits=9, null=True, blank=True)
    ships_from = models.CharField(max_length=100)
    notes = models.TextField(blank=True, default='')
    images = models.TextField(default='[]')
    variants = models.TextField(default='[]')
    extra_data = models.TextField(default='{}')

    def __str__(self):
        return self.title

    def __getattr__(self, attr):
        if attr.startswith('get') and attr.endswith('_dict') or attr.endswith('_list'):
            match = re.match(r'get_(\S+)(_dict|_list)', attr)
            if match:
                def wrapper():
                    model_field = match.group(1)
                    try:
                        cached_model_field = f'_cached_{model_field}'
                        if hasattr(self, cached_model_field):
                            return getattr(self, cached_model_field)

                        value = json.loads(getattr(self, model_field))
                        setattr(self, cached_model_field, value)
                        return value
                    except:
                        if attr.endswith('_list'):
                            return []
                        return {}
                return wrapper

        raise AttributeError

    @property
    def source_url(self):
        return app_link(reverse("prints:source", kwargs={
            'custom_product_id': self.id,
        }))

    @property
    def supplier_name(self):
        return 'Dropified Print'

    @property
    def supplier_url(self):
        return app_link(reverse('prints:index'))

    @cached_property
    def variants_mapping(self):
        get_source_variants_mapping = getattr(self, f'get_{self.product.source_type}_variants_mapping')
        return get_source_variants_mapping()

    def get_layerapp_variants_mapping(self):
        extra_data = self.get_extra_data_dict()
        variants_mapping = extra_data.get('variants_mapping')
        shipments = {
            'title': 'Ships From',
            'values': []
        }
        if self.product.data.get('usa_sku'):
            shipments['values'].append({
                'title': 'United States',
                'image': False,
                'sku': 'from:usa_sku'
            })

        if self.product.data.get('china_sku'):
            shipments['values'].append({
                'title': 'China',
                'image': False,
                'sku': 'from:china_sku'
            })

        if shipments.get('values'):
            variants_mapping.append(shipments)
        return variants_mapping

    def get_variants_info(self):
        variants = self.get_variants_dict()
        variants_info = {}
        for k, v in variants.items():
            if v['title']:
                variants_info[v['title']] = v
        return variants_info

    def get_variants_sku(self):
        extra_data = self.get_extra_data_dict()
        variants_sku = {}

        for k, v in extra_data['styles']['data'].items():
            title = v['title'] or v['style']
            variants_sku[title] = v['sku']

        for k, v in extra_data['sizes']['data'].items():
            title = v['title'] or v['size']
            variants_sku[title] = v['sku']

        return variants_sku

    def get_variants(self):
        extra_data = self.get_extra_data_dict()
        styles = extra_data['styles']
        sizes = extra_data['sizes']

        return [{
            'title': styles['title'],
            'values': [v['title'] or v['style']
                       for k, v in styles['data'].items()
                       if not v.get('deleted')]
        }, {
            'title': sizes['title'],
            'values': [v['title'] or v['size']
                       for k, v in sizes['data'].items()
                       if not v.get('deleted')]
        }]

    def get_variants_images(self):
        extra_data = self.get_extra_data_dict()
        styles = extra_data['styles']['data']
        return {v['image_hash']: v['title'] or v['style'] for k, v in styles.items()}

    def to_api_data(self):
        return dict(
            title=self.title,
            description=self.description,
            type=self.product_type,
            vendor=self.vendor,
            weight=None,
            weight_unit='lbs',
            tags=self.tags,
            get_variants_info=self.get_variants_info(),
            variants_sku=self.get_variants_sku(),
            variants=self.get_variants(),
            variants_images=self.get_variants_images(),
            images=self.get_images_list(),
            price=self.price,
            compare_at_price=self.compare_at,
            original_url=self.source_url,
            published=False,
            store=dict(
                name=self.supplier_name,
                url=self.supplier_url,
            ),
        )

    def get_variants_for_order(self, variants):
        """
        Get original and custom product variants data
        using order_data.variant list from /api/order-data

        :variants: List containing title as string or dict (title, sku)
        """
        if self.product.source_type != 'layerapp':
            raise NotImplementedError('Not a LayerApp custom product')

        extra_data = self.get_extra_data_dict()
        styles = extra_data['styles']['data'].values()
        sizes = extra_data['sizes']['data'].values()
        # Set default title when custom title is empty
        for size in sizes:
            size['title'] = size['title'] if size.get('title') else size.get('size')

        if not styles or not sizes:
            raise Exception('No variants found in this product')

        found_style = None
        found_size = None
        found_shipment = None

        # LayerApp variant ids can be found in custom variants data
        for variant in variants:
            is_dict = isinstance(variant, dict)
            if is_dict and variant.get('sku'):
                for sku in variant.get('sku').split(';'):
                    found_style = next((i for i in styles if sku == i.get('sku')), found_style)
                    found_size = next((i for i in sizes if sku == i.get('sku')), found_size)

                    # Custom "Ships From" from variants mapping
                    if sku in ['from:usa_sku', 'from:china_sku']:
                        found_shipment = sku.replace('from:', '')
            else:
                title = variant.get('title') if is_dict else variant
                title = title.strip()
                found_style = next((i for i in styles if title == i.get('title') or title == i.get('style')), found_style)
                found_size = next((i for i in sizes if title == i.get('title') or title == i.get('size')), found_size)

        if not found_style or not found_size:
            raise Exception('Variant not found')

        # Send original titles to LayerApp
        original_style = next((i for i in self.product.variants.get('styles') if int(found_style['id']) == int(i['id'])), '')
        original_size = next((i for i in self.product.variants.get('sizes') if int(found_size['id']) == int(i['id'])), '')
        if not original_style:
            raise Exception(f'Original style for "{found_style["title"]}" not found')
        if not original_size:
            raise Exception(f'Original size for "{found_size["title"]}" not found')

        # Sizes and original product can have sku related prices
        shipment_sku = original_size.get(found_shipment, self.product.data.get(found_shipment))
        shipment_sku = shipment_sku or self.ships_from

        return {
            'original': {
                'style': original_style,
                'size': original_size,
            },
            'custom': {
                'style': found_style,
                'size': found_size,
                'shipment': shipment_sku,
                'from': self.product.get_country_by_sku(shipment_sku),
            }
        }

    def get_order_item(self, order_data):
        get_source_order_item = getattr(self, f'get_{self.product.source_type}_order_item')
        return get_source_order_item(order_data)

    def get_layerapp_order_item(self, order_data):
        variants_data = self.get_variants_for_order(order_data.get('variant', []))
        prices = self.product.get_price_by_sku(variants_data['custom']['shipment'])

        return dict(
            order_data_id=order_data['id'],
            line_id=order_data['line_id'],
            title=order_data['print_order_info']['line_title'],
            product_id=self.product.source_id,
            custom_product_id=self.id,
            source_sku=variants_data['custom']['shipment'],
            quantity=order_data['quantity'],
            dropified_price=prices['dropified'],
            dropified_profit=prices['dropified_profit'],
            source_price=prices['source'],
            source_profit=prices['source_profit'],
            custom_data=json.dumps(dict(
                style=variants_data['original']['style'],
                size=variants_data['original']['size'],
                printing_images=variants_data['custom']['style']['artworks'],
                sample_images=[variants_data['custom']['style']['image']],
            ))
        )


class Order(models.Model):
    class Meta:
        index_together = ['content_type', 'object_id']
        ordering = '-created_at',

    PENDING_PAYMENT = 'pending_payment'
    PENDING_SHIPMENT = 'pending_shipment'
    SHIPPED = 'shipped'
    PENDING_RETURN = 'pending_return'
    RETURNED = 'returned'

    ORDER_STATUS = (
        (PENDING_PAYMENT, 'Awaiting Payment'),
        (PENDING_SHIPMENT, 'Awaiting Shipment'),
        (SHIPPED, 'Shipped'),
        (PENDING_RETURN, 'Awaiting Return'),
        (RETURNED, 'Returned'),
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    store_object = GenericForeignKey('content_type', 'object_id')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order_name = models.CharField(max_length=200, blank=True, default='', verbose_name="Order ID")  # POD order id
    order_reference = models.CharField(max_length=200)  # Order name from store platform
    order_id = models.BigIntegerField()  # ID from store platform
    source_type = models.CharField(max_length=50, default='layerapp', choices=(('layerapp', 'LayerApp'),))
    status = models.CharField(max_length=50, choices=ORDER_STATUS, default=PENDING_PAYMENT)
    created_at = models.DateTimeField(auto_now=True)

    stripe_transaction_id = models.CharField(max_length=50, null=True, blank=True)
    invoice_url = models.TextField(default='')
    paid_at = models.DateTimeField(null=True, blank=True)
    source_paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Payout Date")
    source_paid_reference = models.CharField(max_length=50, db_index=True, null=True, blank=True, verbose_name="Payout Reference")

    customer_name = models.TextField(blank=True, default='')
    customer_phone = models.CharField(max_length=50, default='', blank=True)
    address1 = models.TextField()
    address2 = models.TextField(default='', null=True)
    city = models.CharField(max_length=255)
    zip_code = models.CharField(max_length=50)
    province = models.CharField(max_length=255)
    country_code = models.CharField(max_length=32)

    tracking_company = models.CharField(max_length=128, blank=True, null=True, default='')
    tracking_number = models.CharField(max_length=128, blank=True, null=True, default='')

    def save(self, *args, **kwargs):
        super(Order, self).save(*args, **kwargs)

        if not self.order_name:
            self.order_name = f'P{self.id + 10000}'
            self.save()

    @property
    def tracking_url(self):
        return app_link(reverse("prints:tracking", kwargs={
            'order_id': self.id,
        }))

    @cached_property
    def to_dict(self):
        get_source_dict = getattr(self, f'get_{self.source_type}_dict')
        return get_source_dict()

    @cached_property
    def total_amount(self):
        return self.line_items.aggregate(total_amount=models.Sum('dropified_price'))['total_amount']

    def get_layerapp_dict(self):
        return {
            'id': self.id,
            'shipment_notification_url': self.tracking_url,
            'address': {
                'address': f'{self.address1} - {self.address2}',
                'city': self.city,
                'zip': self.zip_code,
                'country': self.country_code,
                'customer_name': self.customer_name,
                'phone': self.customer_phone,
                'province': self.province,
            },
            'line_items': [i.to_dict for i in self.line_items.all()]
        }

    def place_stripe_order(self, user):
        assert self.total_amount > 0, "Wrong price while placing order"

        customer = user.stripe_customer.retrieve()
        for line_item in self.line_items.all():
            stripe.InvoiceItem.create(
                customer=customer.id,
                unit_amount=int(line_item.dropified_price * 100),
                quantity=line_item.quantity,
                currency='usd',
                description=line_item.title,
            )

        invoice = stripe.Invoice.create(
            customer=customer.id,
            description='Dropified Print - {} Order'.format(self.order_reference),
            collection_method='charge_automatically',
            metadata=dict(
                source='Dropified Print',
                order_id=self.id,
            )
        )
        response = invoice.pay()

        assert response['paid'], 'Payment failed'
        self.status = self.PENDING_SHIPMENT
        self.stripe_transaction_id = response['id']
        self.invoice_url = response['hosted_invoice_url']
        self.paid_at = timezone.now()
        self.save()


class OrderItem(models.Model):
    track_content_type = models.ForeignKey(ContentType, null=True, on_delete=models.CASCADE)
    track_object_id = models.PositiveIntegerField(blank=True, null=True)
    track = GenericForeignKey('track_content_type', 'track_object_id')
    line_id = models.BigIntegerField()

    order = models.ForeignKey(Order, related_name='line_items', on_delete=models.CASCADE)
    order_data_id = models.CharField(max_length=100)
    title = models.TextField(default='')
    product_id = models.BigIntegerField()
    custom_product = models.ForeignKey(CustomProduct, on_delete=models.CASCADE)

    dropified_price = models.DecimalField(decimal_places=2, max_digits=9, default=0.0)
    dropified_profit = models.DecimalField(decimal_places=2, max_digits=9, default=0.0)
    source_price = models.DecimalField(decimal_places=2, max_digits=9, default=0.0)
    source_profit = models.DecimalField(decimal_places=2, max_digits=9, default=0.0)

    source_sku = models.CharField(max_length=100)  # LayerApp SKU
    quantity = models.IntegerField(default=1)

    # For size, style, printing_images and sample_images
    custom_data = models.TextField(default='{}')

    @cached_property
    def data(self):
        try:
            return json.loads(self.extra_data)
        except:
            return {}

    @cached_property
    def to_dict(self):
        get_source_dict = getattr(self, f'get_{self.order.source_type}_dict')
        return get_source_dict()

    def get_layerapp_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'sku': self.order_data_id,
            'layer_sku': self.source_sku,
            'quantity': self.quantity,
            'size': self.data.get('size'),
            'style': self.data.get('style'),
            'printing_images': self.data.get('printing_images', []),
            'sample_images': self.data.get('sample_images', []),
        }
