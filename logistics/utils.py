import json
from decimal import Decimal

import arrow
import easypost
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.templatetags.static import static
from django.urls import reverse
from django.utils.text import slugify

from lib.exceptions import capture_message, capture_exception
from shopified_core.shipping_helper import country_from_code
from shopified_core.utils import dict_val, hash_text
from shopified_core.models_utils import get_product_model
from .models import Account, CarrierType, Supplier, Product, Variant, Listing, AccountBalance
from .carriers import CARRIERS


class InsufficientFundsError(Exception):
    pass


class OrderError(Exception):
    def __init__(self, message=None):
        super().__init__(message)
        self.message = message


def get_root_easypost_api(debug=settings.DEBUG):
    easypost.api_key = settings.EASYPOST_DEBUG_API_KEY if debug else settings.EASYPOST_API_KEY
    return easypost


def get_logistics_account(user):
    user = user.models_user
    account = user.logistics_accounts.first()
    if account is None:
        account = Account.objects.create(user=user)
        AccountBalance.objects.get_or_create(user=user, defaults={'balance': 0})

    if not account.api_key:
        account.create_source()

    return account


def get_easypost_api(user, debug=settings.DEBUG):
    account = get_logistics_account(user)
    easypost.api_key = account.test_api_key if debug else account.api_key
    return easypost


def get_variant_data(variants):
    if not isinstance(variants, list):
        variants = [variants]

    variant_sku = []
    variant_title = []
    for variant in variants:
        if not isinstance(variant, dict):
            variant_title.append(variant)
        else:
            if 'sku' in variant:
                variant_sku.append(variant['sku'])

            if 'title' in variant and variant['title'] != 'Default Title':
                variant_title.append(variant['title'])

    return variant_title, variant_sku


def get_logistics_variants(variants, existing_variants=None):
    if not isinstance(variants, list):
        variants = [{'values': [{'title': variants, 'sku': ''}], 'title': '', 'sku': ''}]

    existing_variants = existing_variants or []
    new_variants = []
    for variant in variants:
        if isinstance(variant, dict):
            sku = variant.get('sku', '')
            title = variant.get('title', '')
        else:
            sku = ''
            title = variant

        new_variant = existing_variants.pop(0) if len(existing_variants) else {'values': [], 'title': '', 'sku': ''}
        for v in new_variant['values']:
            if title == v['title'] and sku == v['sku']:
                break
        else:
            new_variant['values'].append({'title': variant, 'sku': sku})
        new_variants.append(new_variant)
    return new_variants


def get_carrier_logo(carrier_type):
    carrier = slugify(carrier_type)
    try:
        url = CARRIERS[carrier]
        return static(url)
    except KeyError:
        capture_exception()
        return ''


def get_carrier_types(source='easypost'):
    """
    Each carrier has its own credentials key names to access their API.
    Return carrier specific fields to save into easypost
    """
    carrier_types = CarrierType.objects.filter(source=source).exclude(label__in=['USPS'])
    if source == 'easypost':
        if carrier_types and carrier_types[0].updated_at < arrow.get().shift(days=-1):
            carrier_types.delete()
            carrier_types = []

        if not carrier_types:
            field_types = {
                'visible': 'text',
                'checkbox': 'checkbox',
                'fake': 'text',
                'password': 'password',
                'masked': 'text',
            }

            carriers = []
            for carrier_type in get_root_easypost_api(debug=False).CarrierAccount.types():
                fields = []
                for name, info in carrier_type['fields']['credentials'].to_dict().items():
                    fields.append({
                        'name': name,
                        'label': info['label'],
                        'type': field_types.get(info['visibility'], 'text')
                    })
                carriers.append(CarrierType(
                    label=carrier_type['readable'],
                    name=carrier_type['type'],
                    fields=json.dumps(fields),
                    source=source,
                    logo_url=get_carrier_logo(carrier_type['readable'])
                ))
            CarrierType.objects.bulk_create(carriers)
            carrier_types = CarrierType.objects.filter(source=source)

    return [c.to_dict() for c in carrier_types]


def get_supplier_listing(store, order_data, warehouse, connect_product=False):
    if not order_data.get('source_id') and not connect_product:
        return [None, None]

    supplier = None
    listing = None
    store_type = store.store_type
    models_user = store.user.models_user

    product_source_id = f"{store_type}_{order_data['store']}_{order_data['product_id']}"  # Identifies store product
    suppliers = Supplier.objects.filter(
        models.Q(id=order_data.get('source_id'))
        | models.Q(source_ids__icontains=product_source_id)
    )
    supplier = suppliers.first()
    if supplier is None and connect_product:
        StoreProduct = get_product_model(store_type)
        try:
            store_product = StoreProduct.objects.get(id=order_data['product_id'], store=store)
            defaults = {'image_urls': json.dumps(store_product.get_images())}
        except StoreProduct.DoesNotExist:
            defaults = {}

        product, created = Product.objects.get_or_create(user=models_user, title=order_data['title'], defaults=defaults)
        supplier, created = Supplier.objects.get_or_create(product=product, warehouse_id=warehouse.id, defaults={
            'source_ids': product_source_id
        })
        if not created:
            supplier.source_ids = ','.join(supplier.source_ids.split(',') + [product_source_id])

        if order_data.get('is_raw'):
            supplier.connect_product(store_type, order_data['store'], order_data['product_id'])

    elif supplier.warehouse_id != warehouse.id:
        product = supplier.product
        supplier = suppliers.filter(warehouse=warehouse).first()
        # Suppliers can be added according to warehouse selected in UI
        if supplier is None:
            supplier = Supplier.objects.create(product=product, warehouse=warehouse, source_ids=product_source_id)

    # Order of search for variants:
    # 1. By store's SKU
    # 2. Logistics variant ID
    # 3. Variant's title
    variant = dict_val(order_data, ['variant', 'variants'])
    titles, skus = get_variant_data(variant)
    search_sku = models.Q()
    for sku in skus:
        search_sku &= models.Q(variant__sku=sku)
    listing = supplier.listings.filter(search_sku).first()

    if listing is None:
        if isinstance(variant, dict) and variant.get('id'):
            listing = supplier.listings.filter(id=variant.get('id')).first()

    if listing is None:
        search_title = models.Q()
        for title in titles:
            search_title &= models.Q(variant__title=title)
        listing = supplier.listings.filter(search_title).first()

    if listing is None:
        variant, created = Variant.objects.get_or_create(
            product=supplier.product,
            title=' / '.join(titles),
            sku=';'.join(skus),
        )
        listing = Listing.objects.create(variant=variant, supplier=supplier)

    new_variants = get_logistics_variants(
        dict_val(order_data, ['variant', 'variants']),
        existing_variants=supplier.product.get_variants_map()
    )
    supplier.product.variants_map = json.dumps(new_variants)
    return [supplier, listing]


class Address():
    def __init__(self, user: User, **kwargs):
        self.address_source_id = kwargs.get('address_source_id')
        self.name = kwargs.get('name')
        self.address1 = kwargs['address1']
        self.address2 = kwargs.get('address2')
        self.company = kwargs.get('company')
        self.city = kwargs['city']
        self.province = kwargs['province']
        self.zip = kwargs['zip']
        self.country_code = kwargs['country_code']
        self.country = country_from_code(kwargs['country_code'])
        self.phone = kwargs.get('phone')
        self.user = user
        self.errors = kwargs.get('errors') or ''
        self._hash = None
        self._source_obj = None

    def to_dict(self):
        if self.address_source_id == 'None':
            self.address_source_id = ''
        return {
            'address_source_id': self.address_source_id or '',
            'name': self.name,
            'address1': self.address1 or '',
            'address2': self.address2 or '',
            'company': self.company or '',
            'city': self.city or '',
            'province': self.province or '',
            'zip': self.zip or '',
            'country_code': self.country_code or '',
            'country': self.country or '',
            'phone': self.phone or '',
            'errors': self.errors or ''
        }

    def to_easypost(self):
        return {
            'name': self.name,
            'street1': self.address1,
            'street2': self.address2,
            'city': self.city,
            'state': self.province,
            'zip': self.zip,
            'country': self.country_code,
            'company': self.company,
            'phone': self.phone,
            'verify': ['delivery']
        }

    @property
    def hash(self):
        if not self._hash:
            address = self.to_dict()
            # Address is used in RAW format elsewhere
            address.pop('address_source_id')
            address.pop('errors')
            self._hash = hash_text(json.dumps(address, sort_keys=True))
        return self._hash

    def _easypost(self):
        address = get_easypost_api(self.user).Address.create(**self.to_easypost())

        self.errors = ''
        if not address['verifications']['delivery']['success']:
            delivery = address['verifications']['delivery'].to_dict()
            capture_message('Address is not valid', extra={
                'easypost_errors': delivery
            })
            self.errors = [e['message'] for e in delivery['errors']]
            self.address_source_id = ''
            return self.to_dict()

        self._source_obj = address
        self.address_source_id = address['id']
        return self.to_dict()

    def create(self, source='easypost') -> dict:
        if source == 'easypost':
            return self._easypost()
        else:
            raise NotImplementedError('Source unknown')

    def retrieve(self, source='easypost'):
        if self._source_obj is not None:
            return self._source_obj

        if not self.address_source_id:
            return None

        if source == 'easypost':
            try:
                return get_easypost_api(self.user).Address.retrieve(self.address_source_id)
            except easypost.Error as e:
                if 'not be found' not in str(e):
                    raise e

                self._source_obj = self.create(source)
                return self._source_obj
        else:
            raise NotImplementedError('Source unknown')


class Shipment():
    def __init__(self, order, user: User):
        self.order = order
        self._source_obj = self.order.get_shipment() or {}
        self.user = user.models_user

    def _easypost(self) -> dict:
        if not self.order.weight:
            return {'errors': ['Package weight is missing']}

        if self.order.rate_id or self.order.is_paid:
            return self._source_obj

        to_address = Address(user=self.user, **self.order.get_address())
        saved_to_address = to_address.retrieve()
        if saved_to_address is None:
            self.order.to_address_hash = ''
            self.order.save()
            return {}

        from_address = Address(user=self.user, **self.order.get_address('from'))
        saved_from_address = from_address.retrieve()
        if saved_from_address is None:
            return {}

        shipment = dict(
            to_address=saved_to_address,
            from_address=saved_from_address,
            parcel={
                "length": float(self.order.length) or 0.1,
                "width": float(self.order.width) or 0.1,
                "height": float(self.order.height) or 0.1,
                "weight": float(self.order.weight),
            }
        )

        if to_address.country_code != from_address.country_code:
            customs_items = []
            for item in self.order.items.all():
                customs_items.append({
                    'description': item.title,
                    'quantity': item.quantity,
                    'weight': float(item.weight),
                    'value': float(item.unit_cost * item.quantity),
                    'hs_tariff_number': item.hs_tariff,
                    'origin_country': item.country_code or 'US',
                })
                if not item.weight or not item.hs_tariff:
                    return {'errors': ['Item info for customs is missing']}

            models_user = self.user.models_user
            shipment['customs_info'] = dict(
                eel_pfc='NOEEI 30.37(a)',  # Order total is lower than $2500
                contents_type='merchandise',
                customs_certify=True,
                customs_signer=models_user.get_full_name() or models_user.email,
                restriction_type='none',
                restriction_comments='',
                non_delivery_option='return',
                customs_items=customs_items,
            )

        def is_dropified(carrier):
            return any(c.lower() in carrier.lower() for c in settings.DROPIFIED_CARRIERS)

        result = get_easypost_api(self.user).Shipment.create(**shipment).to_dict()
        result['rates'] = [{
            **r,
            'shipment_id': result['id'],
            'logo': get_carrier_logo(r['carrier']),
            'is_root': False,
        } for r in result['rates'] if not is_dropified(r['carrier'])]

        shipment['to_address'] = to_address.to_easypost()
        shipment['from_address'] = from_address.to_easypost()
        root_shipment = get_root_easypost_api().Shipment.create(**shipment).to_dict()
        result['rates'] += [{
            **r,
            'rate': str((Decimal(r['rate']) * settings.DROPIFIED_RATE_PERCENT).quantize(Decimal('.01'))),
            'shipment_id': root_shipment['id'],
            'logo': get_carrier_logo(r['carrier']),
            'is_root': True,
        } for r in root_shipment['rates'] if is_dropified(r['carrier'])]

        result['rates'] = sorted(result['rates'], key=lambda r: float(r['rate']))
        return result

    def to_dict(self):
        if not self._source_obj:
            return {'errors': [], 'rates': []}

        return {
            'id': self._source_obj['id'],
            'errors': [],  # self._source_obj.get('errors') or [],
            'warnings': [m['message'] for m in self._source_obj.get('messages') or []],
            'rates': self._source_obj['rates'] or []
        }

    def create(self, source='easypost', force=False):
        if not force and self._source_obj:
            return self._source_obj

        # Prevent refresh shipment when label is purchased
        if self._source_obj and self._source_obj.get('postage_label'):
            return self._source_obj

        if source == 'easypost':
            self._source_obj = self._easypost()
            self.order.shipment_data = json.dumps(self._source_obj)
        else:
            raise NotImplementedError('Source unknown')

        return self._source_obj

    def pay(self, source='easypost'):
        if self.order.is_paid:
            return False

        if self._source_obj.get('errors'):
            return False
        else:
            self._source_obj['errors'] = []

        if self._source_obj.get('postage_label'):
            return False

        if not self._source_obj.get('rates'):
            self._source_obj['errors'].append('Error when retrieving rates, try refreshing')
            self.order.shipment_data = json.dumps(self._source_obj)
            self.order.save()
            return False

        if source == 'easypost':
            for rate in self._source_obj['rates']:
                if rate['id'] == self.order.rate_id:
                    break
            else:
                self._source_obj['errors'].append('Rate not found')
                self.order.shipment_data = json.dumps(self._source_obj)
                self.order.save()
                return False

            self.order.is_dropified = rate['is_root']
            if self.order.is_dropified:
                try:
                    balance = self.user.logistics_balance
                except AccountBalance.DoesNotExist:
                    balance = AccountBalance.objects.create(user=self.user, balance=0)

                if Decimal(rate['rate']) > balance.balance:
                    link = f'<a href="{reverse("logistics:orders")}#showBalance" target="_blank">Dropified balance</a>'
                    raise OrderError(f'Add funds to your {link} to use our discounted USPS rates')

                shipment = get_root_easypost_api().Shipment.retrieve(rate['shipment_id'])
            else:
                shipment = get_easypost_api(self.user).Shipment.retrieve(rate['shipment_id'])

            if shipment and not shipment.get('postage_label'):
                try:
                    for rate in shipment['rates']:
                        if rate['id'] == self.order.rate_id:
                            break
                    shipment = shipment.buy(rate=rate).to_dict()
                    if shipment.get('errors'):
                        capture_message('Error paying for shipment', extra={'easypost_errors': shipment['errors']})
                        self._source_obj['errors'] = ['Error when selecting a rate']
                    else:
                        self._source_obj['tracking_code'] = shipment['tracking_code']
                        self._source_obj['postage_label'] = shipment['postage_label']
                        self._source_obj['selected_rate'] = shipment['selected_rate']

                except easypost.Error as e:
                    error_message = e.message.lower()
                    if 'insufficient funds' in error_message:
                        raise OrderError('Insufficient carrier funds to create label')

                    capture_exception()
                    self._source_obj['errors'] = ['Error when selecting a rate']

            if self._source_obj.get('errors'):
                return False

            self.order.shipment_data = json.dumps(self._source_obj)
            self.order.tracking_number = self._source_obj['tracking_code']
            self.order.source_label_url = self._source_obj['postage_label']['label_url']
            self.order.rate_id = self._source_obj['selected_rate']['id']
            self.order.shipment_cost = Decimal(self._source_obj['selected_rate']['rate']) * settings.DROPIFIED_RATE_PERCENT
            self.order.is_paid = True
            if self.order.is_dropified:
                AccountBalance.objects.filter(user=self.user).update(balance=models.F('balance') - self.order.shipment_cost)
            self.order.save()
            return True
        else:
            raise NotImplementedError('Source unknown')
