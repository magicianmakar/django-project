from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.utils.functional import cached_property
from django.core.exceptions import PermissionDenied
from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.db.models import Count, Max, Q, F
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.utils.crypto import get_random_string

import re
import simplejson as json
import requests
import textwrap
import hashlib
from urlparse import urlparse

import arrow
from pusher import Pusher

from stripe_subscription.stripe_api import stripe
from data_store.models import DataStore

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

PLAN_PAYMENT_GATEWAY = (
    ('jvzoo', 'JVZoo'),
    ('stripe', 'Stripe'),
)

SUBUSER_PERMISSIONS = (
    ('edit_settings', 'Edit settings'),
    ('view_product_boards', 'View product boards'),
    ('edit_product_boards', 'Edit product boards'),
    ('view_help_and_support', 'View help and support'),
    ('view_bonus_training', 'View bonus training'),
)

SUBUSER_STORE_PERMISSIONS = (
    ('save_for_later', 'Save products for later'),
    ('send_to_shopify', 'Send products to Shopify'),
    ('delete_products', 'Delete products'),
    ('place_orders', 'Place orders'),
    ('view_alerts', 'View alerts'),
)


def add_to_class(cls, name):
    def _decorator(*args, **kwargs):
        cls.add_to_class(name, args[0])
    return _decorator


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

    company = models.ForeignKey('UserCompany', null=True, blank=True)
    subuser_permissions = models.ManyToManyField('SubuserPermission', blank=True, related_name='user_profiles')

    def __str__(self):
        return '{} | {}'.format(self.user.username, self.plan.title)

    def save(self, *args, **kwargs):
        if self.config:
            json.loads(self.config)

        super(UserProfile, self).save(*args, **kwargs)

    def get_plan(self):
        try:
            return self.plan
        except:
            return None

    def bundles_list(self):
        return map(lambda b: b.replace('Bundle', '').strip(), self.bundles.all().values_list('title', flat=True))

    def apply_registration(self, reg, verbose=False):
        if reg.plan is None and reg.bundle is None:
            return

        if reg.plan:
            self.plan = reg.plan

            if reg.plan.slug == 'subuser-plan':
                self.subuser_parent = reg.sender

            expire = reg.get_data().get('expire_date')
            if expire:
                expire = arrow.get(expire)  # expire is an ISO format date

                if self.plan_expire_at is not None:
                    from django.utils import timezone

                    delta = self.plan_expire_at - timezone.now()
                    if delta.days < 30:
                        # Purchase was made 30 days before the expire date (or after the expire date
                        # usually 1-2 days, since the daily_task will disable expired account)
                        # we will renew the expire date to an other 1 year
                        # TODO: handle dates other than 1 year.
                        self.plan_expire_at = None

                if self.plan_expire_at is None:
                    # Chane to Free Plan after expiration
                    from leadgalaxy.utils import get_plan

                    self.plan_after_expire = get_plan(plan_hash='606bd8eb8cb148c28c4c022a43f0432d')
                    self.plan_expire_at = expire.datetime

            if verbose and self.plan.title != reg.plan:
                print "APPLY REGISTRATION: Change User {} ({}) from '{}' to '{}'".format(
                    self.user.username, self.user.email, self.plan.title, reg.plan.title)

        if reg.bundle:
            self.bundles.add(reg.bundle)

            if verbose:
                print "APPLY REGISTRATION: Add Bundle '{}' to: {} ({})".format(
                    reg.bundle.title, self.user.username, self.user.email)

        self.save()

        if self.subuser_parent:
            permissions = SubuserPermission.objects.filter(store__isnull=True)
            # Subusers have global permissions by default
            self.subuser_permissions.add(*permissions)

        reg.user = self.user
        reg.expired = True
        reg.save()

    def apply_subscription(self, plan, verbose=False):
        from stripe_subscription.utils import update_subscription

        assert plan.is_stripe(), 'Not a Stripe Plan'

        # Assert we have a stripe customer
        self.create_stripe_customer()

        sub = stripe.Subscription.create(
            customer=self.user.stripe_customer.customer_id,
            plan=plan.stripe_plan.stripe_id,
            metadata={'plan_id': plan.id, 'user_id': self.user.id}
        )

        update_subscription(self.user, plan, sub)

        self.plan = plan
        self.save()

    def create_stripe_customer(self):
        ''' Create a Stripe Customer for this a profile '''
        try:
            customer = self.user.stripe_customer
        except:
            customer = None

        if not customer:
            customer = stripe.Customer.create(
                description="Username: {}".format(self.user.username),
                email=self.user.email,
                metadata={'user_id': self.user.id}
            )

            from stripe_subscription.utils import update_customer
            update_customer(self.user, customer)

    def change_plan(self, plan):
        if self.plan != plan:
            self.plan = plan
            self.save()

            return True

        else:
            return False

    def get_active_stores(self, flat=False):
        if self.is_subuser:
            stores = self.subuser_stores.filter(is_active=True)
        else:
            stores = self.user.shopifystore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_new_alerts(self):
        return self.user.models_user.aliexpressproductchange_set \
                                    .filter(seen=False) \
                                    .filter(hidden=False) \
                                    .count()

    @cached_property
    def get_perms(self):
        perms = list(self.plan.permissions.all().values_list('name', flat=True))
        for bundle in self.bundles.all():
            for i in bundle.permissions.values_list('name', flat=True):
                if i not in perms:
                    perms.append(i)

        return perms

    def import_stores(self):
        ''' Return Stores the User can import products from '''

        if self.is_subuser:
            return self.subuser_parent.profile.import_stores()

        stores = []
        for i in self.get_perms:
            if i.endswith('_import.use'):
                name = i.split('_')[0]
                stores.append(name)

        return stores

    def can(self, perm_name, store=None):
        if perm_name[-4:] == '.sub':
            codename = perm_name[:-4]
            return self.has_subuser_permission(codename, store)

        if self.is_subuser:
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

    def get_config_value(self, name=None, default=None):
        if name is None:
            return self.get_config()
        elif type(name) is list:
            config = self.get_config()
            values = []
            for i in name:
                values.append(config.get(i, default))

            return values
        else:
            return self.get_config().get(name, default)

    def set_config_value(self, name, value):
        data = self.get_config()

        if data.get(name) != value:
            data[name] = value

            self.config = json.dumps(data)
            self.save()

    def del_config_values(self, key, startswith=False):
        data = self.get_config()
        for name, val in data.items():
            if key == name or (startswith and name.startswith(key)):
                del data[name]

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

        if self.is_subuser:
            return self.subuser_parent.profile.can_add_store()

        user_stores = int(self.stores)
        if user_stores == -2:
            total_allowed = self.plan.stores  # -1 mean unlimited
        else:
            total_allowed = user_stores

        user_count = self.user.shopifystore_set.filter(is_active=True).count()
        can_add = True

        if (total_allowed > -1) and (user_count + 1 > total_allowed):
            if not self.can('unlimited_stores.use') or self.get_config_value('_limit_stores'):
                can_add = False

        if not can_add and self.plan.is_stripe():
            can_add = len(re.findall(r'\blite\b', self.plan.title, re.I)) == 0

        return can_add, total_allowed, user_count

    def can_add_product(self):
        """ Check if the user plan allow one more product saving """

        if self.is_subuser:
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
        if self.is_subuser:
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

    @property
    def is_subuser(self):
        return self.subuser_parent is not None

    def has_subuser_permission(self, codename, store=None):
        if self.is_subuser:
            permission = self.subuser_permissions.filter(codename=codename)
            if store:
                if not self.subuser_stores.filter(pk=store.id).exists():
                    return False
                permission = permission.filter(store=store)
            if not permission.exists():
                return False
        return True


class UserCompany(models.Model):
    name = models.CharField(max_length=100, blank=True, default='')
    address_line1 = models.CharField(max_length=255, blank=True, default='')
    address_line2 = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    zip_code = models.CharField(max_length=100, blank=True, default='')

    def __unicode__(self):
        return self.name


class SubuserPermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('ShopifyStore', blank=True, null=True, related_name='subuser_permissions')

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __unicode__(self):
        return '{} - {}'.format(self.store.title, self.codename)


@add_to_class(User, 'get_first_name')
def user_first_name(self):
    return self.first_name.title() if self.first_name else self.username


@add_to_class(User, 'can')
def user_can(self, perms, store_id=None):
    return self.profile.can(perms, store_id)


@add_to_class(User, 'get_config')
def user_get_config(self, name=None, default_value=None):
    return self.profile.get_config_value(name, default_value)


@add_to_class(User, 'set_config')
def user_set_config(self, name, value):
    return self.profile.set_config_value(name, value)


@add_to_class(User, 'get_boards')
def user_get_boards(self):
    if self.is_subuser:
        return self.profile.subuser_parent.get_boards()
    else:
        return self.shopifyboard_set.all().order_by('title')


@add_to_class(User, 'is_stripe_customer')
def user_stripe_customer(self):
    try:
        return bool(self.stripe_customer and self.stripe_customer.customer_id)
    except:
        return False


class ShopifyStore(models.Model):
    class Meta:
        ordering = ['list_index', '-created_at']

    title = models.CharField(max_length=512, blank=True, default='')
    currency_format = models.CharField(max_length=50, blank=True, null=True)
    api_url = models.CharField(max_length=512)

    # For OAuth App
    shop = models.CharField(max_length=512, blank=True, null=True)
    access_token = models.CharField(max_length=512, blank=True, null=True)
    scope = models.CharField(max_length=512, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    store_hash = models.CharField(unique=True, default='', max_length=50, editable=False)
    version = models.IntegerField(default=1, choices=((1, 'Private App'), (2, 'Shopify App')), verbose_name='Store Version')

    list_index = models.IntegerField(default=0)
    auto_fulfill = models.CharField(max_length=50, null=True, blank=True)

    user = models.ForeignKey(User)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        try:
            self.auto_fulfill = self.user.get_config('auto_shopify_fulfill', '')
        except User.DoesNotExist:
            pass

        super(ShopifyStore, self).save(*args, **kwargs)

    def __unicode__(self):
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
            url = re.sub('[a-z0-9]*:[a-z0-9]+@', '*:*@', url)

        return url

    def get_api_credintals(self):
        api_key, api_secret = re.findall(r'(\w+):(\w+)', self.api_url).pop()

        return {
            'api_key': api_key,
            'api_secret': api_secret
        }

    def get_orders_count(self, status='open', fulfillment='unshipped', financial='any', query='', all_orders=False):
        if all_orders:
            fulfillment = 'any'
            financial = 'any'
            status = 'any'
            query = ''

        params = {
            'status': status,
            'fulfillment_status': fulfillment,
            'financial_status': financial,
            'query': query
        }

        if query:
            if type(query) is long:
                params['ids'] = [query]
            else:
                params['name'] = query

        return requests.get(
            url=self.get_link('/admin/orders/count.json', api=True),
            params=params
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

    def is_synced(self):
        from shopify_orders.utils import is_store_synced
        return is_store_synced(self)

    def is_sync_enabled(self):
        from shopify_orders.utils import is_store_synced, is_store_sync_enabled
        return is_store_synced(self) and is_store_sync_enabled(self)

    def connected_count(self):
        return self.shopifyproduct_set.exclude(shopify_id=0).count()

    def saved_count(self):
        return self.shopifyproduct_set.filter(shopify_id=0).count()

    def pending_orders(self):
        return self.shopifyorder_set.filter(closed_at=None, cancelled_at=None) \
                                    .filter(Q(fulfillment_status=None) | Q(fulfillment_status='partial')) \
                                    .filter(financial_status='paid') \
                                    .annotate(connected=Max('shopifyorderline__product_id')).filter(connected__gt=0) \
                                    .annotate(tracked=Count('shopifyorderline__track')).exclude(tracked=F('items_count')) \
                                    .count()

    def awaiting_tracking(self):
        return self.shopifyordertrack_set.filter(hidden=False) \
                                         .filter(source_tracking='') \
                                         .exclude(source_status='FINISH') \
                                         .exclude(hidden=True) \
                                         .count()

    def pusher_trigger(self, event, data):
        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        pusher.trigger('order_{}'.format(self.get_short_hash()), event, data)


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
    original_data_key = models.CharField(max_length=32, null=True, blank=True)

    config = models.TextField(null=True, blank=True)
    variants_map = models.TextField(default='', blank=True)
    supplier_map = models.TextField(default='', null=True, blank=True)
    shipping_map = models.TextField(default='', null=True, blank=True)
    mapping_config = models.TextField(null=True, blank=True)

    notes = models.TextField(default='', blank=True)
    shopify_export = models.ForeignKey('ShopifyProductExport', on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    title = models.TextField(blank=True, default='', db_index=True)
    price = models.FloatField(default=0.0)
    product_type = models.CharField(max_length=255, blank=True, default='', db_index=True)
    tag = models.TextField(blank=True, default='', db_index=True)

    parent_product = models.ForeignKey('ShopifyProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Dupliacte of product')

    price_notification_id = models.IntegerField(default=0)

    shopify_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True)
    default_supplier = models.ForeignKey('ProductSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        try:
            title = self.title
            if len(title) > 79:
                return u'{}...'.format(textwrap.wrap(title, width=79)[0])
            elif title:
                return title
            else:
                return u'<ShopifyProduct: %d>' % self.id
        except:
            return u'<ShopifyProduct: %d>' % self.id

    def get_original_data(self):
        if self.original_data_key:
            data_store = DataStore.objects.get(key=self.original_data_key)
            return data_store.data
        return getattr(self, 'original_data', '{}')

    def set_original_data(self, value, clear_original=False):
        if self.original_data_key:
            data_store = DataStore.objects.get(key=self.original_data_key)
            data_store.data = value
            data_store.save()
        else:
            while True:
                data_key = hashlib.md5(get_random_string(32)).hexdigest()

                try:
                    DataStore.objects.get(key=data_key)
                    continue  # Retry an other key

                except DataStore.DoesNotExist:
                    # the key is unique
                    DataStore.objects.create(key=data_key, data=value)

                    self.original_data_key = data_key

                    if clear_original:
                        self.original_data = ''

                    self.save()

                    break

    def save(self, *args, **kwargs):
        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tag = data.get('tags', '')[:1024]
        self.product_type = data.get('type', '')[:254]

        try:
            self.price = '%.02f' % float(data['price'])
        except:
            self.price = 0.0

        super(ShopifyProduct, self).save(*args, **kwargs)

    def get_config(self):
        try:
            return json.loads(self.config)
        except:
            return {}

    def is_connected(self):
        return bool(self.get_shopify_id())

    def have_supplier(self):
        try:
            return self.default_supplier is not None
        except:
            return False

    def shopify_link(self):
        shopify_id = self.get_shopify_id()

        if shopify_id:
            return self.store.get_link('/admin/products/{}'.format(shopify_id))
        else:
            return None

    def get_shopify_id(self):
        return self.shopify_id if self.store else None

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
        supplier = self.default_supplier
        if supplier:
            info = {
                'name': supplier.supplier_name or '',
                'url': supplier.supplier_url or ''
            }

            if info.get('url').startswith('//'):
                info['url'] = u'http:{}'.format(info['url'])

            return info

        data = json.loads(self.data)
        return data.get('store')

    def set_original_url(self, url, commit=False):
        data = json.loads(self.data)
        data['original_url'] = url
        self.data = json.dumps(data)

        if commit:
            self.save()

    def set_default_supplier(self, supplier, commit=False):
        self.default_supplier = supplier

        if commit:
            self.save()

        self.get_suppliers().update(is_default=False)

        supplier.is_default = True
        supplier.save()

    def set_variant_mapping(self, mapping, supplier=None, update=False):
        if supplier is None:
            supplier = self.default_supplier

        if update:
            try:
                current = json.loads(supplier.variants_map)
            except:
                current = {}

            for k, v in mapping.items():
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        if supplier:
            supplier.variants_map = mapping
            supplier.save()
        else:
            self.variants_map = mapping
            self.save()

    def get_variant_mapping(self, name=None, default=None, for_extension=False, supplier=None, mapping_supplier=False):
        mapping = {}

        if supplier is None:
            if mapping_supplier:
                supplier = self.get_suppier_for_variant(name)
            else:
                supplier = self.default_supplier

        try:
            if supplier and supplier.variants_map:
                mapping = json.loads(supplier.variants_map)
            elif self.variants_map:
                mapping = json.loads(self.variants_map)
            else:
                mapping = {}
        except:
            mapping = {}

        if name:
            mapping = mapping.get(str(name), default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        if for_extension and type(mapping) in [str, unicode]:
            mapping = mapping.split(',')

        return mapping

    def get_all_variants_mapping(self):
        from leadgalaxy.utils import get_shopify_product

        all_mapping = {}

        shopify_id = self.get_shopify_id()
        if not shopify_id:
            return None

        shopify_product = get_shopify_product(self.store, shopify_id)
        if not shopify_product:
            return None

        for supplier in self.get_suppliers():
            variants_map = self.get_variant_mapping(supplier=supplier)

            seen_variants = []
            for i, v in enumerate(shopify_product['variants']):
                mapped = variants_map.get(str(v['id']))
                if mapped:
                    options = mapped
                else:
                    options = []
                    if v.get('option1') and v.get('option1').lower() != 'default title':
                        options.append(v.get('option1'))
                    if v.get('option2'):
                        options.append(v.get('option2'))
                    if v.get('option3'):
                        options.append(v.get('option3'))

                    options = map(lambda a: {'title': a}, options)

                try:
                    if type(options) not in [list, dict]:
                        options = json.loads(options)

                        if type(options) is int:
                            options = str(options)
                except:
                    pass

                variants_map[str(v['id'])] = options
                seen_variants.append(str(v['id']))

            for k in variants_map.keys():
                if k not in seen_variants:
                    del variants_map[k]

            all_mapping[str(supplier.id)] = variants_map

        return all_mapping

    def get_shopify_exports(self):
        shopify_id = self.get_shopify_id()
        if shopify_id:
            return ShopifyProductExport.objects.filter(
                Q(shopify_id=self.shopify_export.shopify_id, store__user=self.user) |
                Q(product=self))
        else:
            return ShopifyProductExport.objects.filter(product=self)

    def get_real_variant_id(self, variant_id):
        """
        Used to get current variant id from previously delete variant id
        """

        config = self.get_config()
        if config.get('real_variant_map'):
            return config.get('real_variant_map').get(str(variant_id), variant_id)

        return variant_id

    def get_suppliers(self):
        return self.productsupplier_set.all().order_by('-is_default')

    def get_mapping_config(self):
        try:
            return json.loads(self.mapping_config)
        except:
            return {}

    def set_mapping_config(self, config):
        if type(config) is not str:
            config = json.dumps(config)

        self.mapping_config = config
        self.save()

    def set_suppliers_mapping(self, mapping):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.supplier_map = mapping
        self.save()

    def get_suppliers_mapping(self, name=None, default=None):
        mapping = {}
        try:
            if self.supplier_map:
                mapping = json.loads(self.supplier_map)
            else:
                mapping = {}
        except:
            mapping = {}

        if name:
            mapping = mapping.get(str(name), default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        return mapping

    def get_suppier_for_variant(self, variant_id):
        """
            Return the mapped Supplier for the given variant_id
            or the default one if mapping is not set/found
        """

        config = self.get_mapping_config()
        mapping = self.get_suppliers_mapping(name=variant_id)

        if not variant_id or not mapping or config.get('supplier') == 'default':
            return self.default_supplier

        try:
            return self.productsupplier_set.get(id=mapping['supplier'])
        except:
            return self.default_supplier

    def get_shipping_for_variant(self, supplier_id, variant_id, country_code):
        """ Return Shipping Method for the given variant_id and country_code """
        mapping = self.get_shipping_mapping(supplier=supplier_id, variant=variant_id)

        if variant_id and country_code and mapping and type(mapping) is list:
            for method in mapping:
                if country_code == method.get('country'):
                    short_name = method.get('method_name').split(' ')
                    if len(short_name) > 1 and short_name[1].lower() in ['post', 'seller\'s', 'aliexpress']:
                        method['method_short'] = ' '.join(short_name[:2])
                    else:
                        method['method_short'] = short_name[0]

                    if method['country'] == 'GB':
                        method['country'] = 'UK'

                    return method

        return None

    def set_shipping_mapping(self, mapping, update=True):
        if update:
            try:
                current = json.loads(self.shipping_map)
            except:
                current = {}

            for k, v in mapping.items():
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.shipping_map = mapping
        self.save()

    def get_shipping_mapping(self, supplier=None, variant=None, default=None):
        mapping = {}
        try:
            if self.shipping_map:
                mapping = json.loads(self.shipping_map)
            else:
                mapping = {}
        except:
            mapping = {}

        if supplier and variant:
            mapping = mapping.get('{}_{}'.format(supplier, variant), default)

        try:
            mapping = json.loads(mapping)
        except:
            pass

        if type(mapping) is int:
            mapping = str(mapping)

        return mapping

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        product_data = json.loads(self.data)

        product_data.update(data)

        self.data = json.dumps(product_data)


class ProductSupplier(models.Model):
    store = models.ForeignKey(ShopifyStore, null=True)
    product = models.ForeignKey(ShopifyProduct)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        if self.supplier_name:
            return self.supplier_name
        elif self.supplier_url:
            return self.supplier_url
        else:
            return u'<ProductSupplier: {}>'.format(self.id)

    def get_source_id(self):
        try:
            if 'aliexpress.com' in self.product_url.lower():
                return int(re.findall('[/_]([0-9]+).html', self.product_url)[0])
        except:
            return None

    def short_product_url(self):
        source_id = self.get_source_id()
        if source_id:
            if 'aliexpress.com' in self.product_url.lower():
                return u'http://www.aliexpress.com/item//{}.html'.format(source_id)

        return self.product_url

    def support_auto_fulfill(self):
        """
        Return True if this supplier support auto fulfill using the extension
        Currently only Aliexpress support that
        """

        return 'aliexpress.com/' in self.product_url.lower()

    def get_name(self):
        if self.supplier_name and self.supplier_name.strip():
            name = self.supplier_name.strip()
        else:
            supplier_idx = 1
            for i in self.product.get_suppliers():
                if self.id == i.id:
                    break
                else:
                    supplier_idx += 1

            name = u'Supplier #{}'.format(supplier_idx)

        return name


class ShopifyProductExport(models.Model):
    class Meta:
        ordering = ['-created_at']

    store = models.ForeignKey(ShopifyStore)
    product = models.ForeignKey(ShopifyProduct, null=True)

    shopify_id = models.BigIntegerField(default=0, verbose_name='Shopify Product ID')
    original_url = models.CharField(max_length=512, blank=True, default='')
    supplier_name = models.CharField(max_length=512, null=True, blank=True, default='')
    supplier_url = models.CharField(max_length=512, null=True, blank=True, default='')
    is_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')

    def __unicode__(self):
        return u'{}'.format(self.shopify_id)

    def shopify_url(self):
        return self.store.get_link('/admin/products/{}'.format(self.shopify_id))


class ShopifyProductImage(models.Model):
    product = models.BigIntegerField(verbose_name="Shopify Product ID")
    variant = models.BigIntegerField(default=0, verbose_name="Shopify Product ID")
    store = models.ForeignKey(ShopifyStore)

    image = models.CharField(max_length=512, blank=True, default='')

    def __unicode__(self):
        return u'{} | {}'.format(self.product, self.variant)


class ShopifyOrderTrack(models.Model):
    class Meta:
        ordering = ['-created_at']
        index_together = ['store', 'order_id', 'line_id']

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

    def get_tracking_link(self):
        aftership_domain = 'http://track.aftership.com/{{tracking_number}}'

        if type(self.user.get_config('aftership_domain')) is dict:
            aftership_domain = self.user.get_config('aftership_domain').get(str(self.store_id), aftership_domain)

            if '{{tracking_number}}' not in aftership_domain:
                aftership_domain = "http://{}.aftership.com/{{{{tracking_number}}}}".format(aftership_domain)
            elif not aftership_domain.startswith('http'):
                aftership_domain = 'http://{}'.format(re.sub('^([:/]*)', r'', aftership_domain))

        return aftership_domain.replace('{{tracking_number}}', self.source_tracking)

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

    def __unicode__(self):
        return u'{} | {}'.format(self.order_id, self.line_id)


class ShopifyBoard(models.Model):
    class Meta:
        ordering = ['title']

    title = models.CharField(max_length=512, blank=True, default='')
    config = models.CharField(max_length=512, blank=True, default='')

    user = models.ForeignKey(User)
    products = models.ManyToManyField(ShopifyProduct, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.title

    def saved_count(self):
        return self.products.filter(shopify_id=0).count()

    def connected_count(self):
        return self.products.exclude(shopify_id=0).count()


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

    def __unicode__(self):
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

    def __unicode__(self):
        return self.description


class ClippingMagic(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.OneToOneField(User, related_name='clippingmagic')

    api_id = models.CharField(max_length=100, default='', verbose_name='ClippingMagic API ID')
    api_secret = models.CharField(max_length=255, default='', verbose_name='ClippingMagic API Secret')

    allowed_images = models.IntegerField(default=-1)
    downloaded_images = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return '%s:%s' % (self.api_id, self.api_secret)


class GroupPlan(models.Model):
    title = models.CharField(max_length=512, blank=True, default='', verbose_name="Plan Title")
    slug = models.SlugField(unique=True, max_length=30, verbose_name="Plan Slug")

    stores = models.IntegerField(default=0)
    products = models.IntegerField(default=0)
    boards = models.IntegerField(default=0)
    register_hash = models.CharField(unique=True, max_length=50, editable=False)

    badge_image = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='', verbose_name='Plan name visible to users')
    notes = models.TextField(null=True, blank=True, verbose_name='Admin Notes')
    features = models.TextField(null=True, blank=True, verbose_name='Features List')

    default_plan = models.IntegerField(default=0, choices=YES_NO_CHOICES)

    permissions = models.ManyToManyField(AppPermission, blank=True)

    payment_gateway = models.CharField(max_length=25, choices=PLAN_PAYMENT_GATEWAY, default=PLAN_PAYMENT_GATEWAY[0][0])
    hidden = models.BooleanField(default=False, verbose_name='Hidden from users')

    def save(self, *args, **kwargs):
        if not self.register_hash:
            self.register_hash = get_random_string(32, 'abcdef0123456789')

        super(GroupPlan, self).save(*args, **kwargs)

    def permissions_count(self):
        return self.permissions.count()

    def get_description(self):
        desc = self.description if self.description else self.title
        if self.is_stripe():
            desc = '{} (${}/month)'.format(desc, self.stripe_plan.amount, self.stripe_plan.interval)

        return desc

    def import_stores(self):
        ''' Return Stores this allow importing products from '''

        stores = []
        for i in self.permissions.all():
            if i.name.endswith('_import.use'):
                name = i.name.split('_')[0]
                stores.append(name)

        return stores

    def is_stripe(self):
        try:
            return self.payment_gateway == 'stripe' and bool(self.stripe_plan.stripe_id)
        except:
            return False

    @property
    def is_free(self):
        return self.slug in ['free-stripe-plan', 'free-plan']

    @property
    def large_badge_image(self):
        return self.badge_image.replace('_small.', '.')

    def __unicode__(self):
        return self.title


class FeatureBundle(models.Model):
    title = models.CharField(max_length=30, verbose_name="Bundle Title")
    slug = models.SlugField(unique=True, max_length=30, verbose_name="Bundle Slug")
    register_hash = models.CharField(unique=True, max_length=50, editable=False)
    description = models.CharField(max_length=512, blank=True, default='')
    hidden_from_user = models.BooleanField(default=False, verbose_name='Hide in User Profile')

    permissions = models.ManyToManyField(AppPermission, blank=True)

    def save(self, *args, **kwargs):
        if not self.register_hash:
            self.register_hash = get_random_string(32, 'abcdef0123456789')

        super(FeatureBundle, self).save(*args, **kwargs)

    def permissions_count(self):
        return self.permissions.count()

    def get_description(self):
        return self.description if self.description else self.title

    def __unicode__(self):
        return self.title


class UserUpload(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User)
    product = models.ForeignKey(ShopifyProduct, null=True)
    url = models.CharField(max_length=512, blank=True, default='', verbose_name="Upload file URL")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
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
        if not self.register_hash:
            self.register_hash = get_random_string(32, 'abcdef0123456789')

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
                'used': data['used_count'],
                'expire_in_days': data.get('expire_in_days')
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

    def get_description(self):
        if self.plan:
            return self.plan.get_description()
        elif self.bundle:
            return self.bundle.get_description()
        else:
            return None

    def __unicode__(self):
        if self.plan:
            return u'Plan: {}'.format(self.plan.title)
        elif self.bundle:
            return u'Bundle: {}'.format(self.bundle.title)
        else:
            return u'<PlanRegistration: {}>'.format(self.id)


class AliexpressProductChange(models.Model):
    class Meta:
        ordering = ['-updated_at']
        index_together = ['user', 'seen', 'hidden']

    user = models.ForeignKey(User, null=True)
    product = models.ForeignKey(ShopifyProduct)
    hidden = models.BooleanField(default=False, verbose_name='Archived change')
    seen = models.BooleanField(default=False, verbose_name='User viewed the changes')
    data = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return u'{}'.format(self.id)

    def orders_count(self, open=True):
        return self.product.shopifyorderline_set \
                           .exclude(order__fulfillment_status='fulfilled') \
                           .filter(order__closed_at=None, order__cancelled_at=None) \
                           .count()


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

    def __unicode__(self):
        return u'{} | {}'.format(self.provider, self.payment_id)


def user_is_subsuser(self):
    return self.profile.is_subuser


def user_models_user(self):
    if not self.profile.is_subuser:
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
                store = obj.store
            else:
                store = None

            if store:
                stores = self.profile.get_active_stores(flat=True)
                if store.id not in stores:
                    raise PermissionDenied("You don't have autorization to edit this store.")

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(abs(hash('add'))))


def user_can_view(self, obj):
    if self.is_superuser:
        return True
    elif not self.is_subuser:
        can = obj.user == self
    else:
        can = obj.user == self.profile.subuser_parent
        if can:
            if isinstance(obj, ShopifyStore):
                store = obj
            elif hasattr(obj, 'store'):
                store = obj.store
            else:
                store = None

            if store:
                stores = self.profile.get_active_stores(flat=True)
                if store.id not in stores:
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
                store = obj.store
            else:
                store = None

            if store:
                stores = self.profile.get_active_stores(flat=True)
                if store.id not in stores:
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
def invalidate_acp_users(sender, instance, created, **kwargs):
    cache.set('template.cache.acp_users.invalidate', True, timeout=3600)

    if not created and not instance.is_subuser:
        instance.get_active_stores().update(auto_fulfill=instance.get_config_value('auto_shopify_fulfill', ''))


@receiver(post_save, sender=ShopifyOrderTrack)
def invalidate_orders_status(sender, instance, created, **kwargs):
    cache.delete(make_template_fragment_key('orders_status', [instance.store_id]))


@receiver(post_save, sender=User)
def userprofile_creation(sender, instance, created, **kwargs):
    if created:
        plan = GroupPlan.objects.filter(default_plan=1).first()
        if not plan:
            plan = GroupPlan.objects.create(title='Default Plan', slug='default-plan', default_plan=1)

        UserProfile.objects.create(user=instance, plan=plan)

    if not created and instance.is_stripe_customer():
        try:
            customer = instance.stripe_customer
            email = json.loads(customer.data).get('email')

            if email != instance.email:
                cus = stripe.Customer.retrieve(customer.customer_id)
                cus.email = instance.email

                customer.stripe_save(cus)
        except:
            from raven.contrib.django.raven_compat.models import client as raven_client
            raven_client.captureException()


@receiver(post_save, sender=ShopifyStore)
def add_store_permissions(sender, instance, created, **kwargs):
    if created:
        for codename, name in SUBUSER_STORE_PERMISSIONS:
            SubuserPermission.objects.create(store=instance, codename=codename, name=name)


@receiver(m2m_changed, sender=UserProfile.subuser_stores.through)
def add_store_permissions_to_subuser(sender, instance, pk_set, action, **kwargs):
    if action == "post_add":
        stores = ShopifyStore.objects.filter(pk__in=pk_set)
        for store in stores:
            permissions = store.subuser_permissions.all()
            instance.subuser_permissions.add(*permissions)


@receiver(m2m_changed, sender=UserProfile.subuser_permissions.through)
def clear_cached_template(sender, instance, pk_set, action, **kwargs):
    permission_pks = SubuserPermission.objects.filter(
        Q(codename='view_help_and_support') | Q(codename='view_bonus_training')
    ).values_list('pk', flat=True)

    if set(permission_pks) & set(pk_set):
        key = make_template_fragment_key('sidebar_link', [instance.user.id, instance.plan_id])
        cache.delete(key)
