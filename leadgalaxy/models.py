from django.db import models

from django.contrib.auth.models import User
from django.utils.functional import cached_property
from django.core.exceptions import PermissionDenied
from django.db.models.signals import post_save
from django.dispatch import receiver

import re
import simplejson as json
import requests
import textwrap
from urlparse import urlparse

ENTITY_STATUS_CHOICES = (
    (0, 'Pending'),
    (1, 'Active'),
    (2, 'Inactive'),
    (3, 'Hold'),
)

YES_NO_CHOICES = (
    (0, 'No'),
    (1, 'Yes'),
)


class UserProfile(models.Model):
    user = models.OneToOneField(User, related_name='profile')
    plan = models.ForeignKey('GroupPlan', null=True, on_delete=models.SET_NULL)
    bundles = models.ManyToManyField('FeatureBundle', blank=True)

    subuser_parent = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='subuser_parent')
    subuser_stores = models.ManyToManyField('ShopifyStore', blank=True, related_name='subuser_stores')

    stores = models.IntegerField(default=-2)
    products = models.IntegerField(default=-2)
    boards = models.IntegerField(default=-2)

    status = models.IntegerField(default=1, choices=ENTITY_STATUS_CHOICES)

    country = models.CharField(max_length=255, blank=True, default='')
    timezone = models.CharField(max_length=255, null=True, blank=True, default='')
    emails = models.TextField(null=True, blank=True, default='', verbose_name="Other Emails")

    config = models.TextField(default='', blank=True)

    plan_expire_at = models.DateTimeField(blank=True, null=True, verbose_name="Plan Expire Date")
    plan_after_expire = models.ForeignKey('GroupPlan', blank=True, null=True, related_name="expire_plan",
                                          on_delete=models.SET_NULL, verbose_name="Plan to user after Expire Date")

    def __str__(self):
        return '{} | {}'.format(self.user.username, self.plan.title)

    def get_plan(self):
        try:
            return self.plan
        except:
            return None

    def apply_registration(self, reg, verbose=False):
        if reg.plan is None and reg.bundle is None:
            return

        if reg.plan:
            self.plan = reg.plan

            if reg.plan.slug == 'subuser-plan':
                self.subuser_parent = reg.sender

            expire = reg.get_data().get('expire_date')
            if expire:
                import arrow
                from django.utils import timezone
                from leadgalaxy.utils import get_plan

                expire = arrow.get(expire)  # expire is an ISO format date

                if self.plan_expire_at is not None:
                    delta = self.plan_expire_at - timezone.now()
                    if delta.days < 30:
                        # Purchase was made 30 days before the expire date (or after the expire date
                        # usually 1-2 days, since the daily_task will disable expired account)
                        # we will renew the expire date to an other 1 year
                        # TODO: handle dates other than 1 year.
                        self.plan_expire_at = None

                if self.plan_expire_at is None:
                    # Chane to Free Plan after expiration
                    self.plan_after_expire = get_plan(plan_hash='606bd8eb8cb148c28c4c022a43f0432d')
                    self.plan_expire_at = expire.datetime

            if verbose:
                print "APPLY REGISTRATION: Change User {} ({}) from '{}' to '{}'".format(
                    self.user.username, self.user.email, self.plan.title, reg.plan.title)

        if reg.bundle:
            self.bundles.add(reg.bundle)

            if verbose:
                print "APPLY REGISTRATION: Add Bundle '{}' to: {} ({})".format(
                    reg.bundle.title, self.user.username, self.user.email)

        self.save()

        reg.user = self.user
        reg.expired = True
        reg.save()

    def get_active_stores(self, flat=False):
        if self.user.is_subuser:
            stores = self.subuser_stores.all()
        else:
            stores = self.user.shopifystore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_new_alerts(self):
        return self.user.models_user.aliexpressproductchange_set.filter(seen=False).count()

    @cached_property
    def get_perms(self):
        perms = list(self.plan.permissions.all().values_list('name', flat=True))
        for bundle in self.bundles.all():
            for i in bundle.permissions.values_list('name', flat=True):
                if i not in perms:
                    perms.append(i)

        return perms

    def can(self, perm_name):
        if self.subuser_parent is not None:
            return self.subuser_parent.profile.can(perm_name)

        perm_name = perm_name.lower()
        view_perm = perm_name.replace('.use', '.view')
        use_perm = perm_name.replace('.view', '.use')
        for i in self.get_perms:
            i = i.lower()
            if perm_name.endswith('.view'):
                if i == view_perm or i == use_perm:
                    return True
            else:
                if i == perm_name:
                    return True

        return self.user.is_superuser

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def get_config_value(self, name, default=None):
        if type(name) is list:
            config = self.get_config()
            values = []
            for i in name:
                values.append(config.get(i, default))

            return values
        else:
            return self.get_config().get(name, default)

    def set_config_value(self, name, value):
        data = self.get_config()
        data[name] = value

        self.config = json.dumps(data)
        self.save()

    def add_email(self, email):
        try:
            emails = json.loads(self.emails)
        except:
            emails = []

        emails.append(email)

        self.emails = json.dumps(emails)
        self.save()

    def can_add_store(self):
        """ Check if the user plan allow him to add a new store """

        if self.user.is_subuser:
            return self.subuser_parent.profile.can_add_store()

        user_stores = int(self.stores)
        if user_stores == -2:
            total_allowed = self.plan.stores  # -1 mean unlimited
        else:
            total_allowed = user_stores

        user_count = self.user.shopifystore_set.filter(is_active=True).count()
        can_add = True

        if (total_allowed > -1) and (user_count + 1 > total_allowed):
            if not self.can('unlimited_stores.use'):
                can_add = False

        return can_add, total_allowed, user_count

    def can_add_product(self):
        """ Check if the user plan allow one more product saving """

        if self.user.is_subuser:
            return self.subuser_parent.profile.can_add_product()

        user_products = int(self.products)
        if user_products == -2:
            total_allowed = self.plan.products  # -1 mean unlimited
        else:
            total_allowed = user_products

        user_count = self.user.shopifyproduct_set.count()
        can_add = True

        if (total_allowed > -1) and (user_count + 1 > total_allowed):
            if not self.can('unlimited_products.use'):
                can_add = False

        return can_add, total_allowed, user_count

    def can_add_board(self):
        if self.user.is_subuser:
            return self.subuser_parent.profile.can_add_board()

        user_boards = int(self.boards)
        if user_boards == -2:
            total_allowed = self.plan.boards  # -1 mean unlimited
        else:
            total_allowed = user_boards

        user_count = self.user.shopifyboard_set.count()
        can_add = True

        if (total_allowed > -1) and (user_count + 1 > total_allowed):
            if not self.can('unlimited_boards.use'):
                can_add = False

        return can_add, total_allowed, user_count


def user_can(self, perms):
    return self.profile.can(perms)


def user_get_config(self, name, default_value=None):
    return self.profile.get_config_value(name, default_value)


def user_set_config(self, name, value):
    return self.profile.set_config_value(name, value)


def user_get_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_boards()
    else:
        return self.shopifyboard_set.all().order_by('title')


User.add_to_class("can", user_can)
User.add_to_class("get_config", user_get_config)
User.add_to_class("set_config", user_set_config)
User.add_to_class("get_boards", user_get_boards)


class ShopifyStore(models.Model):
    class Meta:
        ordering = ['-created_at']

    title = models.CharField(max_length=512, blank=True, default='')
    api_url = models.CharField(max_length=512)
    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(unique=True, default='', max_length=50, editable=False)

    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def save(self, *args, **kwargs):
        from hashlib import md5
        import uuid

        if not self.store_hash:
            self.store_hash = md5(str(uuid.uuid4())).hexdigest()

        super(ShopifyStore, self).save(*args, **kwargs)

    def __str__(self):
        return self.title

    def get_link(self, page=None, api=False):
        if api:
            url = re.findall('[^/]+@[^@\.]+\.myshopify\.com', self.api_url)[0]
        else:
            url = re.findall('[^@\.]+\.myshopify\.com', self.api_url)[0]

        if page:
            url = 'https://{}/{}'.format(url, page.lstrip('/'))
        else:
            url = 'https://{}'.format(url)

        return url

    def get_api_url(self, hide_keys=False):
        url = self.api_url

        if not url.startswith('http'):
            url = 'https://%s' % url

        if hide_keys:
            url = re.sub('[a-z0-9]+:[a-z0-9]+@', '*:*@', url)

        return url

    def get_api_credintals(self):
        api_key, api_secret = re.findall(r'(\w+):(\w+)', self.api_url).pop()

        return {
            'api_key': api_key,
            'api_secret': api_secret
        }

    def get_orders_count(self, status='open', fulfillment='unshipped', financial='any', query=''):
        return requests.get(
            url=self.get_link('/admin/orders/count.json', api=True),
            params={
                'status': status,
                'fulfillment_status': fulfillment,
                'financial_status': financial,
                'query': query
            }
        ).json().get('count', 0)

    @cached_property
    def get_info(self):
        rep = requests.get(url=self.get_link('/admin/shop.json', api=True))
        rep = rep.json()

        if 'shop' in rep:
            return rep['shop']
        else:
            raise Exception(rep['errors'])

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''


class AccessToken(models.Model):
    class Meta:
        ordering = ['-created_at']

    token = models.CharField(max_length=512, unique=True)
    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.token


class ShopifyProduct(models.Model):
    class Meta:
        ordering = ['-created_at']

    store = models.ForeignKey(ShopifyStore, blank=True, null=True)
    user = models.ForeignKey(User)

    data = models.TextField()
    original_data = models.TextField(default='', blank=True)
    variants_map = models.TextField(default='', blank=True)
    notes = models.TextField(default='', blank=True)
    shopify_export = models.ForeignKey('ShopifyProductExport', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    title = models.CharField(max_length=512, blank=True, default='', db_index=True)
    price = models.FloatField(default=0.0)
    product_type = models.CharField(max_length=255, blank=True, default='', db_index=True)
    tag = models.CharField(max_length=255, blank=True, default='', db_index=True)

    parent_product = models.ForeignKey('ShopifyProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Dupliacte of product')

    price_notification_id = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        try:
            title = json.loads(self.data)['title']
            if len(title) > 79:
                return u'{}...'.format(textwrap.wrap(title, width=79)[0])
            else:
                return u'{}'.format(title)
        except:
            return u'<ShopifyProduct: %d>' % self.id

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data['title']
        self.product_type = data['type']
        self.tag = data['tags']

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(ShopifyProduct, self).save(*args, **kwargs)

    def shopify_link(self):
        shopif_id = self.get_shopify_id()

        if shopif_id:
            return self.store.get_link('/admin/products/{}'.format(shopif_id))
        else:
            return None

    def get_shopify_id(self):
        try:
            if self.shopify_export and self.shopify_export.shopify_id:
                return self.shopify_export.shopify_id
            else:
                return None
        except:
            return None

    def get_source_id(self):
        """
        Return product source id (ex. Aliexpress Product ID)
        """

        try:
            original_url = self.get_original_info()['url']
            original_id = re.findall('[/_]([0-9]+).html', original_url)[0]
            return original_id
        except:
            return None

    def get_product(self):
        try:
            return json.loads(self.data)['title']
        except:
            return None

    def get_images(self):
        return json.loads(self.data)['images']

    def get_original_info(self, url=None):
        if not url:
            data = json.loads(self.data)
            url = data.get('original_url')

        if url:
            # Extract domain name
            domain = urlparse(url).hostname
            if domain is None:
                return domain

            for i in ['com', 'co.uk', 'org', 'net']:
                domain = domain.replace('.%s' % i, '')

            domain = domain.split('.')[-1]

            return {
                'domain': domain,
                'source': domain.title(),
                'url': url
            }

        return {}

    def get_supplier_info(self):
        data = json.loads(self.data)
        return data.get('store')

    def set_original_url(self, url):
        data = json.loads(self.data)
        if url != data.get('original_url'):
            data['original_url'] = url
            self.data = json.dumps(data)
            self.save()

            return True

        return False

    def set_shopify_id_from_url(self, url):
        if url and url.strip():
            try:
                pid = re.findall('/([0-9]+)$', url)[0]
            except:
                return False
        else:
            pid = 0

        if self.shopify_export:
            self.shopify_export.shopify_id = pid
            self.shopify_export.save()

        return pid

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        product_data = json.loads(self.data)

        product_data.update(data)

        self.data = json.dumps(product_data)


class ShopifyProductExport(models.Model):
    class Meta:
        ordering = ['-created_at']

    original_url = models.CharField(max_length=512, blank=True, default='')
    shopify_id = models.BigIntegerField(default=0, verbose_name='Shopify Product ID')

    store = models.ForeignKey(ShopifyStore)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')

    def __str__(self):
        return '{}'.format(self.shopify_id)


class ShopifyProductImage(models.Model):
    product = models.BigIntegerField(verbose_name="Shopify Product ID")
    variant = models.BigIntegerField(default=0, verbose_name="Shopify Product ID")
    store = models.ForeignKey(ShopifyStore)

    image = models.CharField(max_length=512, blank=True, default='')

    def __unicode__(self):
        return '{} | {}'.format(self.product, self.variant)


class ShopifyOrder(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User)
    store = models.ForeignKey(ShopifyStore, null=True)
    order_id = models.BigIntegerField()
    line_id = models.BigIntegerField()
    shopify_status = models.CharField(max_length=128, blank=True, null=True, default='',
                                      verbose_name="Shopify Fulfillment Status")

    source_id = models.BigIntegerField(default=0, verbose_name="Source Order ID")
    source_status = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Order Status")
    source_tracking = models.CharField(max_length=128, blank=True, default='', verbose_name="Source Tracking Number")
    hidden = models.BooleanField(default=False)
    auto_fulfilled = models.BooleanField(default=False, verbose_name='Automatically fulfilled')
    seen = models.BooleanField(default=False, verbose_name='User viewed the changes')
    check_count = models.IntegerField(default=0)
    data = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')
    status_updated_at = models.DateTimeField(auto_now_add=True, verbose_name='Last Status Update')

    def encoded(self):
        return json.dumps(self.data).encode('base64')

    def get_shopify_link(self):
        return self.store.get_link('/admin/orders/{}'.format(self.order_id))

    def get_source_status(self):
        status_map = {
            "PLACE_ORDER_SUCCESS": "Awaiting Payment",
            "IN_CANCEL": "Awaiting Cancellation",
            "WAIT_SELLER_SEND_GOODS": "Awaiting Shipment",
            "SELLER_PART_SEND_GOODS": "Partial Shipment",
            "WAIT_BUYER_ACCEPT_GOODS": "Awaiting delivery",
            "WAIT_GROUP_SUCCESS": "Pending operation success",
            "FINISH": "Order Completed",
            "IN_ISSUE": "Dispute Orders",
            "IN_FROZEN": "Frozen Orders",
            "WAIT_SELLER_EXAMINE_MONEY": "Payment not yet confirmed",
            "RISK_CONTROL": "Payment being verified",
            "IN_PRESELL_PROMOTION": "Promotion is on",
        }

        return status_map.get(self.source_status)

    get_source_status.admin_order_field = 'source_status'

    def get_source_status_color(self):
        if not self.source_status:
            return 'danger'
        elif self.source_status == 'FINISH':
            return 'primary'
        else:
            return 'warning'

    def get_source_url(self):
        if self.source_id:
            return 'http://trade.aliexpress.com/order_detail.htm?orderId={}'.format(self.source_id)
        else:
            return None

    def __str__(self):
        return '{} | {}'.format(self.order_id, self.line_id)


class ShopifyBoard(models.Model):
    class Meta:
        ordering = ['title']

    title = models.CharField(max_length=512, blank=True, default='')
    config = models.CharField(max_length=512, blank=True, default='')

    user = models.ForeignKey(User)
    products = models.ManyToManyField(ShopifyProduct, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')


class ShopifyWebhook(models.Model):
    class Meta:
        ordering = ['-created_at']
        unique_together = ('store', 'topic')

    store = models.ForeignKey(ShopifyStore)
    topic = models.CharField(max_length=64)
    token = models.CharField(max_length=64)
    shopify_id = models.BigIntegerField(default=0, verbose_name='Webhook Shopify ID')
    call_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.token

    def detach(self):
        """ Remove the webhook from Shopify """

        if not self.shopify_id:
            return

        import requests
        endpoint = self.store.get_link('/admin/webhooks/{}.json'.format(self.shopify_id), api=True)
        try:
            requests.delete(endpoint)
        except Exception as e:
            print 'WEBHOOK: detach excption', repr(e)
            return None


class AppPermission(models.Model):
    name = models.CharField(max_length=512, verbose_name="Permission")
    description = models.CharField(max_length=512, blank=True, default='', verbose_name="Permission Description")

    def __str__(self):
        return self.description


class GroupPlan(models.Model):
    title = models.CharField(max_length=512, blank=True, default='', verbose_name="Plan Title")
    slug = models.SlugField(unique=True, max_length=30, verbose_name="Plan Slug")

    montly_price = models.FloatField(default=0.0, verbose_name="Price Per Month")
    stores = models.IntegerField(default=0)
    products = models.IntegerField(default=0)
    boards = models.IntegerField(default=0)
    register_hash = models.CharField(unique=True, max_length=50, editable=False)

    badge_image = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='')

    default_plan = models.IntegerField(default=0, choices=YES_NO_CHOICES)

    permissions = models.ManyToManyField(AppPermission, blank=True)

    def save(self, *args, **kwargs):
        from hashlib import md5
        import uuid

        if not self.register_hash:
            self.register_hash = md5(str(uuid.uuid4())).hexdigest()

        super(GroupPlan, self).save(*args, **kwargs)

    def permissions_count(self):
        return self.permissions.count()

    def __str__(self):
        return self.title


class FeatureBundle(models.Model):
    title = models.CharField(max_length=30, verbose_name="Bundle Title")
    slug = models.SlugField(unique=True, max_length=30, verbose_name="Bundle Slug")
    register_hash = models.CharField(unique=True, max_length=50, editable=False)
    description = models.CharField(max_length=512, blank=True, default='')
    hidden_from_user = models.BooleanField(default=False, verbose_name='Hide in User Profile')

    permissions = models.ManyToManyField(AppPermission, blank=True)

    def save(self, *args, **kwargs):
        from hashlib import md5
        import uuid

        if not self.register_hash:
            self.register_hash = md5(str(uuid.uuid4())).hexdigest()

        super(FeatureBundle, self).save(*args, **kwargs)

    def permissions_count(self):
        return self.permissions.count()

    def __str__(self):
        return self.title


class UserUpload(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User)
    product = models.ForeignKey(ShopifyProduct, null=True)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.url.replace('%2F', '/').split('/')[-1]


class PlanRegistration(models.Model):
    class Meta:
        ordering = ['-created_at']

    plan = models.ForeignKey(GroupPlan, blank=True, null=True, on_delete=models.SET_NULL, verbose_name='Purchased Plan')
    bundle = models.ForeignKey(FeatureBundle, blank=True, null=True, on_delete=models.SET_NULL, verbose_name='Purchased Bundle')

    user = models.ForeignKey(User, blank=True, null=True)
    sender = models.ForeignKey(User, blank=True, null=True, related_name='sender', verbose_name='Plan Generated By')
    email = models.CharField(blank=True, default='', max_length=120)
    register_hash = models.CharField(max_length=40, unique=True, editable=False)
    data = models.TextField(blank=True, default='')
    expired = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def save(self, *args, **kwargs):
        from hashlib import md5
        import uuid

        if not self.register_hash:
            self.register_hash = md5(str(uuid.uuid4())).hexdigest()

        super(PlanRegistration, self).save(*args, **kwargs)

    def get_data(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    def get_email(self):
        email = self.email
        if not email:
            try:
                data = json.loads(self.data)
                email = data['email']
            except:
                pass

        return email

    def get_usage_count(self):
        try:
            data = json.loads(self.data)
            return {
                'allowed': data['allowed_count'],
                'used': data['used_count']
            }
        except:
            return None

    def set_used_count(self, used):
        data = json.loads(self.data)
        data['used_count'] = used

        self.data = json.dumps(data)

    def add_user(self, user_id):
        data = json.loads(self.data)
        users = data.get('users', [])
        users.append(user_id)

        data['users'] = users

        self.data = json.dumps(data)

    def __str__(self):
        if self.plan:
            return 'Plan: {}'.format(self.plan.title)
        elif self.bundle:
            return 'Bundle: {}'.format(self.bundle.title)
        else:
            return '<PlanRegistration: {}>'.format(self.id)


class AliexpressProductChange(models.Model):
    class Meta:
        ordering = ['-updated_at']

    user = models.ForeignKey(User, null=True)
    product = models.ForeignKey(ShopifyProduct)
    hidden = models.BooleanField(default=False, verbose_name='Archived change')
    seen = models.BooleanField(default=False, verbose_name='User viewed the changes')
    data = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return '{}'.format(self.id)


class PlanPayment(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User, null=True)
    fullname = models.CharField(blank=True, max_length=120)
    email = models.CharField(blank=True, max_length=120)
    provider = models.CharField(max_length=50)
    payment_id = models.CharField(max_length=120)
    transaction_type = models.CharField(blank=True, max_length=32)
    data = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return '{} | {}'.format(self.provider, self.payment_id)


def user_is_subsuser(self):
    return self.profile.subuser_parent is not None


def user_models_user(self):
    if not self.is_subuser:
        return self
    else:
        return self.profile.subuser_parent


def user_can_add(self, obj):
    if not self.is_subuser:
        can = obj.user == self
    else:
        if isinstance(obj, ShopifyStore):
            raise PermissionDenied('Sub-User can not add new stores')

        can = obj.user == self.profile.subuser_parent

        if can:
            if hasattr(obj, 'store'):
                store = obj.store.id
            else:
                store = None

            if store:
                stores = self.profile.get_active_stores(flat=True)
                if store not in stores:
                    raise PermissionDenied("You don't have autorization to edit this store.")

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(abs(hash('add'))))


def user_can_view(self, obj):
    if not self.is_subuser:
        can = obj.user == self
    else:
        can = obj.user == self.profile.subuser_parent
        if can:
            if isinstance(obj, ShopifyStore):
                store = obj.id
            elif hasattr(obj, 'store'):
                store = obj.store.id
            else:
                store = None

            if store:
                stores = self.profile.get_active_stores(flat=True)
                if store not in stores:
                    raise PermissionDenied("You don't have autorization to view this store.")

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(hash('view')))


def user_can_edit(self, obj):
    if not self.is_subuser:
        can = obj.user == self
    else:
        if isinstance(obj, ShopifyStore):
            raise PermissionDenied('Sub-User can not edit stores')

        can = obj.user == self.profile.subuser_parent
        if can:
            if hasattr(obj, 'store'):
                store = obj.store.id
            else:
                store = None

            if store:
                stores = self.profile.get_active_stores(flat=True)
                if store not in stores:
                    raise PermissionDenied("You don't have autorization to view this store.")

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(hash('edit')))


def user_can_delete(self, obj):
    if not self.is_subuser:
        can = obj.user == self
    else:
        if isinstance(obj, ShopifyStore):
            raise PermissionDenied('Sub-User can not delete stores')

        can = obj.user == self.profile.subuser_parent

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(hash('delete')))


User.add_to_class("is_subuser", cached_property(user_is_subsuser))
User.add_to_class("models_user", cached_property(user_models_user))

User.add_to_class("can_add", user_can_add)
User.add_to_class("can_view", user_can_view)
User.add_to_class("can_edit", user_can_edit)
User.add_to_class("can_delete", user_can_delete)


# Signals Handling

@receiver(post_save, sender=UserProfile)
def invalidate_side_bar(sender, instance, created, **kwargs):
    from django.core.cache import cache
    cache.delete_pattern('template.cache.acp_users.*')
