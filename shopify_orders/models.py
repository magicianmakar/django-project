import arrow
import simplejson as json

from django.db import models
from django.contrib.auth.models import User

from leadgalaxy.models import (
    ShopifyStore,
    ShopifyProduct,
    ShopifyOrderTrack
)

SYNC_STATUS = (
    (0, 'Pending'),
    (1, 'Started'),
    (2, 'Completed'),
    (3, 'Unauthorized'),
    (4, 'Error'),
    (5, 'Disabled'),
    (6, 'Reset'),
)


class ShopifySyncStatus(models.Model):
    store = models.ForeignKey(ShopifyStore)
    sync_type = models.CharField(max_length=32)
    sync_status = models.IntegerField(default=0, choices=SYNC_STATUS)
    orders_count = models.IntegerField(default=0)
    pending_orders = models.TextField(blank=True, null=True)
    revision = models.IntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    elastic = models.BooleanField(default=False)

    def __unicode__(self):
        return u'{} / {}'.format(self.sync_type, self.store.title)

    def add_pending_order(self, order_id, commit=True):
        try:
            pending_orders = self.pending_orders.split(',')
        except:
            pending_orders = []

        order_id = str(order_id)
        if order_id not in pending_orders:
            pending_orders.append(order_id)
            self.pending_orders = ','.join(pending_orders)

            if commit:
                self.save()

    def pop_pending_orders(self, commit=True):
        try:
            pending_orders = self.pending_orders.split(',')
        except:
            pending_orders = []

        if len(pending_orders):
            order = pending_orders.pop()
            self.pending_orders = ','.join(pending_orders)
        else:
            order = None

        if commit:
            self.save()

        return order


class ShopifyOrder(models.Model):
    class Meta:
        unique_together = ('store', 'order_id')

    user = models.ForeignKey(User)
    store = models.ForeignKey(ShopifyStore)

    order_id = models.BigIntegerField()
    order_number = models.IntegerField()
    total_price = models.FloatField()

    customer_id = models.BigIntegerField()
    customer_name = models.CharField(max_length=256, blank=True, null=True, default='')
    customer_email = models.CharField(max_length=256, blank=True, null=True, default='')

    financial_status = models.CharField(max_length=32, blank=True, null=True, default='')
    fulfillment_status = models.CharField(max_length=32, blank=True, null=True, default='')

    tags = models.TextField(blank=True, null=True, default='')
    city = models.CharField(max_length=64, blank=True, null=True, default='')
    zip_code = models.CharField(max_length=32, blank=True, null=True, default='')
    country_code = models.CharField(max_length=32, blank=True, null=True, default='')

    items_count = models.IntegerField(blank=True, null=True, verbose_name='Item Lines count')
    need_fulfillment = models.IntegerField(blank=True, null=True, verbose_name='Item Lines not ordered yet')
    connected_items = models.IntegerField(blank=True, null=True, verbose_name='Item Lines with connect products')

    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    def __unicode__(self):
        return u'#{} | {}'.format(self.order_number + 1000, self.store.title)

    def to_dict(self):
        return {
            'store_id': self.store.id,
            'store_title': self.store.title,
            'order_id': self.order_id,
            'order_number': self.order_number,
            'total_price': self.total_price,
            'customer_id': self.customer_id,
            'customer_name': self.customer_name,
            'customer_email': self.customer_email,
            'financial_status': self.financial_status,
            'fulfillment_status': self.fulfillment_status,
        }


class ShopifyOrderLine(models.Model):
    class Meta:
        unique_together = ('order', 'line_id')

    order = models.ForeignKey(ShopifyOrder)
    product = models.ForeignKey(ShopifyProduct, null=True, on_delete=models.deletion.SET_NULL)
    track = models.ForeignKey(ShopifyOrderTrack, null=True, on_delete=models.deletion.SET_NULL)

    line_id = models.BigIntegerField()
    shopify_product = models.BigIntegerField()
    title = models.TextField(blank=True, null=True, default='')
    price = models.FloatField()
    quantity = models.IntegerField()
    fulfillment_status = models.TextField(blank=True, null=True)

    variant_id = models.BigIntegerField()
    variant_title = models.TextField(blank=True, null=True, default='')

    def __unicode__(self):
        return u'{}'.format(self.variant_title)


class ShopifyOrderShippingLine(models.Model):
    store = models.ForeignKey(ShopifyStore)
    order = models.ForeignKey(ShopifyOrder, related_name='shipping_lines')
    shipping_line_id = models.BigIntegerField()
    price = models.FloatField()
    title = models.CharField(max_length=256, null=True, blank=True, db_index=True)
    code = models.CharField(max_length=256, null=True, blank=True)
    source = models.CharField(max_length=256, null=True, blank=True)
    phone = models.CharField(max_length=256, null=True, blank=True)
    carrier_identifier = models.CharField(max_length=256, null=True, blank=True)
    requested_fulfillment_service_id = models.CharField(max_length=256, null=True, blank=True)

    def __unicode__(self):
        return self.title


class ShopifyOrderVariant(models.Model):
    store = models.ForeignKey(ShopifyStore)
    changed_by = models.ForeignKey(User, null=True, on_delete=models.deletion.SET_NULL)

    order_id = models.BigIntegerField(verbose_name='Shopify Order ID')
    line_id = models.BigIntegerField(verbose_name='Shopify Line ID')

    variant_id = models.BigIntegerField()
    variant_title = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return '{}'.format(self.variant_title)


class ShopifyOrderRisk(models.Model):
    store = models.ForeignKey(ShopifyStore)
    order_id = models.BigIntegerField()
    data = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __unicode__(self):
        return u'OrderRisk #{}'.format(self.order_id)

    def get_data(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    def set_data(self, data):
        if type(data) is not str:
            data = json.dumps(data)

        self.data = data
        self.save()


class ShopifyOrderLogManager(models.Manager):
    def update_order_log(self, **kwargs):
        order_log, created = self.update_or_create(
            store=kwargs.pop('store'),
            order_id=kwargs.pop('order_id'),
        )

        order_log.add_log(**kwargs)

        return order_log


class ShopifyOrderLog(models.Model):
    store = models.ForeignKey(ShopifyStore)
    order_id = models.BigIntegerField()
    logs = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ShopifyOrderLogManager()

    def __unicode__(self):
        return u'Log: #{}'.format(self.order_id)

    def add_log(self, log, user, line_id=None, level=None, icon=None, commit=True):
        log_time = arrow.utcnow().timestamp

        logs = self.get_logs(sort=False)
        log = {
            'time': log_time,
            'log': log,
            'user': user.id if user else 0
        }

        if line_id:
            log['line'] = line_id

        if level:
            log['level'] = level

        if icon:
            log['icon'] = icon

        logs.append(log)

        self.logs = json.dumps(logs)

        if commit:
            self.save()

    def get_logs(self, sort='desc', pretty=False, include_webhooks=False):
        try:
            logs = json.loads(self.logs)
        except:
            return []

        if include_webhooks:
            order = ShopifyOrder.objects.filter(store=self.store, order_id=self.order_id).first()
            if order:
                logs.append({
                    'log': 'Order Created in Shopify',
                    'time': arrow.get(order.created_at).timestamp,
                    'icon': 'flag',
                    'user': 0
                })

        if sort:
            logs = sorted(logs, cmp=lambda a, b: cmp(a['time'], b['time']), reverse=bool(sort == 'desc'))

        if pretty:
            for idx, log in enumerate(logs):
                if log['user']:
                    logs[idx]['user'] = User.objects.get(id=log['user'])

        return logs
