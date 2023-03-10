import arrow
import hashlib
import re
import requests
import simplejson as json
from pusher import Pusher
from urllib.parse import urlparse
from operator import attrgetter

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.db.models import Q, Sum
from django.utils.crypto import get_random_string
from django.utils.functional import cached_property

from lib.exceptions import capture_exception
from data_store.models import DataStore
from leadgalaxy.graphql import ShopifyGraphQL
from product_alerts.utils import monitor_product
from shopified_core.decorators import add_to_class
from shopified_core.models import BoardBase, OrderTrackBase, ProductBase, StoreBase, SupplierBase, UserUploadBase
from shopified_core.utils import app_link, get_domain, safe_int, url_join, using_store_db
from stripe_subscription.stripe_api import stripe

SHOPIFY_API_VERSION = "2022-07"

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

PLOD_SHOW_CHOICES = (
    (0, 'Don\'t show for PLOD'),
    (1, 'Show for PLOD only'),
    (3, 'Show For All Users'),
)

PLAN_PAYMENT_GATEWAY = (
    ('jvzoo', 'JVZoo'),
    ('stripe', 'Stripe'),
    ('shopify', 'Shopify'),
)

PLAN_PAYMENT_TYPE = (
    ('monthly', 'Monthly'),
    ('yearly', 'Yearly'),
    ('lifetime', 'Lifetime'),
)

SUBUSER_PERMISSIONS = (
    ('edit_settings', 'Edit settings'),
    ('edit_custom_description', 'Edit custom description'),
    ('edit_advanced_markup', 'Edit advanced mark up rules'),
    ('view_product_boards', 'View product boards'),
    ('edit_product_boards', 'Edit product boards'),
    ('view_help_and_support', 'View help and support'),
    ('view_bonus_training', 'View bonus training'),
    ('view_profit_dashboard', 'View profit dashboard'),
    ('use_callflex', 'CallFlex Access'),
    ('place_private_label_orders', 'Place Private Label Orders'),
    ('place_alibaba_orders', 'Place Alibaba Orders'),
)

SUBUSER_STORE_PERMISSIONS_BASE = (
    ('save_for_later', 'Save products for later'),
    ('delete_products', 'Delete products'),
    ('place_orders', 'Place orders'),
    ('view_alerts', 'View alerts'),
)

SUBUSER_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_shopify', 'Send products to Shopify'),
)

SUBUSER_CHQ_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_chq', 'Send products to CHQ'),
    ('view_profit_dashboard', 'View profit dashboard')
)

SUBUSER_WOO_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_woo', 'Send products to WooCommerce'),
    ('view_profit_dashboard', 'View profit dashboard')
)

SUBUSER_GEAR_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_gear', 'Send products to GearBubble'),
)

SUBUSER_GKART_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_gkart', 'Send products to GrooveKart'),
    ('view_profit_dashboard', 'View profit dashboard'),
)

SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_bigcommerce', 'Send products to BigCommerce'),
    ('view_profit_dashboard', 'View profit dashboard')
)

SUBUSER_EBAY_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_ebay', 'Send products to eBay'),
    ('view_profit_dashboard', 'View profit dashboard'),
)

SUBUSER_FB_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_facebook', 'Send products to Facebook'),
    ('view_profit_dashboard', 'View profit dashboard'),
)

SUBUSER_GOOGLE_STORE_PERMISSIONS = (
    *SUBUSER_STORE_PERMISSIONS_BASE,
    ('send_to_google', 'Send products to Google'),
    ('view_profit_dashboard', 'View profit dashboard'),
)

PRICE_MARKUP_TYPES = (
    ('margin_percent', 'Increase by percentage'),
    ('margin_amount', 'Increase by amount'),
    ('fixed_amount', 'Set to fixed amount'),
)


class UserProfile(models.Model):
    user = models.OneToOneField(User, related_name='profile', on_delete=models.CASCADE)
    plan = models.ForeignKey('GroupPlan', null=True, on_delete=models.SET_NULL)
    bundles = models.ManyToManyField('FeatureBundle', blank=True)
    addons = models.ManyToManyField('addons_core.Addon', blank=True)

    subuser_parent = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='subuser_parent')
    subuser_stores = models.ManyToManyField('ShopifyStore', blank=True, related_name='subuser_stores')
    subuser_chq_stores = models.ManyToManyField('commercehq_core.CommerceHQStore', blank=True, related_name='subuser_chq_stores')
    subuser_woo_stores = models.ManyToManyField('woocommerce_core.WooStore', blank=True, related_name='subuser_woo_stores')
    subuser_ebay_stores = models.ManyToManyField('ebay_core.EbayStore', blank=True, related_name='subuser_ebay_stores')
    subuser_fb_stores = models.ManyToManyField('facebook_core.FBStore', blank=True, related_name='subuser_fb_stores')
    subuser_google_stores = models.ManyToManyField('google_core.GoogleStore', blank=True, related_name='subuser_google_stores')
    subuser_gear_stores = models.ManyToManyField('gearbubble_core.GearBubbleStore', blank=True, related_name='subuser_gear_stores')
    subuser_gkart_stores = models.ManyToManyField('groovekart_core.GrooveKartStore', blank=True, related_name='subuser_gkart_stores')
    subuser_bigcommerce_stores = models.ManyToManyField('bigcommerce_core.BigCommerceStore', blank=True, related_name='subuser_bigcommerce_stores')
    subuser_sd_accounts = models.ManyToManyField('suredone_core.SureDoneAccount', blank=True, related_name='subuser_sd_accounts')
    subuser_fb_marketplace_stores = models.ManyToManyField('fb_marketplace_core.FBMarketplaceStore',
                                                           blank=True, related_name='subuser_fb_marketplace_stores')

    stores = models.IntegerField(default=-2)
    suredone_stores = models.IntegerField(default=-2)
    products = models.IntegerField(default=-2)
    boards = models.IntegerField(default=-2)
    unique_supplements = models.IntegerField(default=-2)
    user_supplements = models.IntegerField(default=-2)
    label_upload_limit = models.IntegerField(default=-2)
    sub_users_limit = models.IntegerField(default=-2)

    status = models.IntegerField(default=1, choices=ENTITY_STATUS_CHOICES)

    country = models.CharField(max_length=255, blank=True, default='')
    timezone = models.CharField(max_length=255, null=True, blank=True, default='')
    emails = models.TextField(null=True, blank=True, default='', verbose_name="Other Emails")
    ips = models.TextField(null=True, blank=True, verbose_name="User IPs")
    tags = models.TextField(null=True, blank=True, verbose_name="User Tags")

    config = models.TextField(default='', blank=True)
    sync_delay_notify = models.IntegerField(default=0, null=True, db_index=True, verbose_name='Notify if no tracking number is found (days)')
    shopify_app_store = models.BooleanField(default=False, verbose_name='User Register from Shopify App Store')
    private_label = models.BooleanField(null=True, default=False, verbose_name='Using Private Label App')
    dropified_private_label = models.BooleanField(null=True, default=False, verbose_name='PLOD user on Dropified App')

    index_products = models.BooleanField(default=False, null=True, verbose_name='Index user products')

    plan_expire_at = models.DateTimeField(blank=True, null=True, verbose_name="Plan Expire Date")
    plan_after_expire = models.ForeignKey('GroupPlan', blank=True, null=True, related_name="expire_plan",
                                          on_delete=models.SET_NULL, verbose_name="Plan to user after Expire Date")

    company = models.ForeignKey('UserCompany', null=True, blank=True, on_delete=models.SET_NULL)
    address = models.ForeignKey('UserAddress', related_name='profile', null=True, blank=True, on_delete=models.SET_NULL)

    has_churnzero_account = models.BooleanField(default=False)

    subuser_permissions = models.ManyToManyField('SubuserPermission', blank=True)
    subuser_chq_permissions = models.ManyToManyField('SubuserCHQPermission', blank=True)
    subuser_woo_permissions = models.ManyToManyField('SubuserWooPermission', blank=True)
    subuser_gear_permissions = models.ManyToManyField('SubuserGearPermission', blank=True)
    subuser_gkart_permissions = models.ManyToManyField('SubuserGKartPermission', blank=True)
    subuser_bigcommerce_permissions = models.ManyToManyField('SubuserBigCommercePermission', blank=True)
    subuser_ebay_permissions = models.ManyToManyField('SubuserEbayPermission', blank=True)
    subuser_fb_permissions = models.ManyToManyField('SubuserFBPermission', blank=True)
    subuser_google_permissions = models.ManyToManyField('SubuserGooglePermission', blank=True)

    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    supplier = models.ForeignKey('product_common.ProductSupplier',
                                 related_name='linked_supplier',
                                 null=True,
                                 blank=True,
                                 on_delete=models.SET_NULL,
                                 verbose_name="Linked Supplier")
    warehouse_account = models.ForeignKey('supplements.ShipStationAccount', related_name='linked_warehouse', null=True,
                                          blank=True, on_delete=models.SET_NULL, verbose_name="Linked Warehouse")

    onboarding_level = models.IntegerField(default=1, null=True, verbose_name='Onboarding Level')

    def __str__(self):
        return f'<UserProfile: {self.id}>'

    @property
    def has_product(self):
        return any([
            self.user.shopifyproduct_set.exists(),
            self.user.commercehqproduct_set.exists(),
            self.user.wooproduct_set.exists(),
            self.user.ebayproduct_set.exists(),
            self.user.fbproduct_set.exists(),
            self.user.googleproduct_set.exists(),
            self.user.gearbubbleproduct_set.exists(),
            self.user.groovekartproduct_set.exists(),
            self.user.bigcommerceproduct_set.exists(),
        ])

    @property
    def has_product_on_board(self):
        return any([
            self.user.shopifyboard_set.filter(products__isnull=False).exists(),
            self.user.commercehqboard_set.filter(products__isnull=False).exists(),
            self.user.wooboard_set.filter(products__isnull=False).exists(),
            self.user.ebayboard_set.filter(products__isnull=False).exists(),
            self.user.fbboard_set.filter(products__isnull=False).exists(),
            self.user.gearbubbleboard_set.filter(products__isnull=False).exists(),
            self.user.groovekartboard_set.filter(products__isnull=False).exists(),
            self.user.bigcommerceboard_set.filter(products__isnull=False).exists(),
        ])

    @property
    def show_order_banner(self):
        config = {}
        if self.config:
            config = json.loads(self.config)

        return config.get('show_order_banner', False)

    def save(self, *args, **kwargs):
        if self.config:
            config = json.loads(self.config)

            have_issue = []
            for k in config.keys():
                if re.match(r'^[0-9_]+$', k) or k in ['extra_images', 'import']:
                    # make sure product mapping/config is not saved to profile config
                    have_issue.append(k)

            if have_issue:
                print(f'Profile containx an error {self.user.email} keys: {",".join(have_issue)}')

            sync_delay_notify = safe_int(config.get('sync_delay_notify_days'))
            if not config.get('sync_delay_notify'):
                sync_delay_notify = 0

            if self.sync_delay_notify != sync_delay_notify:
                self.sync_delay_notify = sync_delay_notify

            self.config = json.dumps(config, indent=2)

        super().save(*args, **kwargs)

    def get_plan(self):
        try:
            return self.plan
        except:
            return None

    def ensure_has_plan(self):
        if self.plan is None:
            self.plan = GroupPlan.objects.get(default_plan=1)
            self.save()

    def bundles_list(self):
        return [b.replace('Bundle', '').strip() for b in self.bundles.all().values_list('title', flat=True)]

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

            if verbose and self.plan.id != reg.plan.id:
                print("APPLY REGISTRATION: Change User {} ({}) from '{}' to '{}'".format(
                    self.user.username, self.user.email, self.plan.title, reg.plan.title))

        if reg.bundle:
            self.bundles.add(reg.bundle)

            if verbose:
                print("APPLY REGISTRATION: Add Bundle '{}' to: {} ({})".format(
                    reg.bundle.title, self.user.username, self.user.email))

        self.save()

        if self.subuser_parent:
            self.have_global_permissions()

        reg.user = self.user
        reg.expired = True
        reg.save()

    def have_global_permissions(self):
        permissions = SubuserPermission.objects.filter(store__isnull=True)
        self.subuser_permissions.add(*permissions)

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

    def create_stripe_customer(self, source=None):
        ''' Create a Stripe Customer for this a profile '''
        from stripe_subscription.utils import update_customer

        try:
            customer = self.user.stripe_customer
        except:
            customer = None

        if not customer:
            customer = stripe.Customer.create(
                description="Username: {}".format(self.user.username),
                email=self.user.email,
                metadata={'user_id': self.user.id},
                source=source
            )

            update_customer(self.user, customer)

        elif source:
            customer = self.user.stripe_customer.retrieve()
            customer.source = source
            customer.save()

            update_customer(self.user, customer)

    def change_plan(self, plan):
        if self.plan != plan:
            self.plan = plan
            self.save()

            return True

        else:
            return False

    def get_stores(self, request=None, sync=True):
        platforms = ['shopify', 'woo', 'chq', 'bigcommerce', 'gear', 'gkart', 'ebay', 'fb', 'google']

        onboarded = bool(re.match(f"/({'|'.join(platforms)})?/?$", request.path)) if request else False

        stores = {
            'shopify': list(self.get_shopify_stores()),
            'chq': list(self.get_chq_stores()),
            'woo': list(self.get_woo_stores()),
            'ebay': list(self.get_ebay_stores(do_sync=sync)),
            'fb': list(self.get_fb_stores(do_sync=sync, include_non_onboarded=onboarded, use_cached=True)),
            'google': list(self.get_google_stores(do_sync=sync, use_cached=True)),
            'gear': list(self.get_gear_stores()),
            'gkart': list(self.get_gkart_stores()),
            'bigcommerce': list(self.get_bigcommerce_stores()),
            'fb_marketplace': list(self.get_fb_marketplace_stores()),
            'all': [],
            'grouped': {},
            'type_count': 0,
        }

        for key, val in stores.items():
            if key not in ['all', 'type_count'] and len(val):
                stores['all'].extend(val)
                stores['type_count'] += 1

        sort_key = 'list_index' if any([v.list_index for v in stores['all']]) else 'created_at'
        stores['all'] = sorted(stores['all'], key=attrgetter(sort_key))
        stores['first'] = stores['all'][0] if stores['type_count'] > 0 else None

        for platform in platforms:
            if len(stores[platform]):
                stores['grouped'][platform] = stores[platform]

        return stores

    def get_shopify_stores(self, flat=False):
        if self.is_subuser:
            stores = self.subuser_stores.filter(is_active=True)
        else:
            stores = self.user.shopifystore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_chq_stores(self, flat=False):
        if self.is_subuser:
            stores = self.subuser_chq_stores.filter(is_active=True)
        else:
            stores = self.user.commercehqstore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_woo_stores(self, flat=False):
        if self.is_subuser:
            stores = self.subuser_woo_stores.filter(is_active=True)
        else:
            stores = self.user.woostore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_ebay_stores(self, flat=False, do_sync=False, use_cached=False):
        if self.is_subuser:
            stores = self.subuser_ebay_stores.filter(is_active=True)
        else:
            stores = self.user.ebaystore_set.filter(is_active=True)

        if do_sync and len(stores):
            # The function is defined in ebay_core.utils.py
            self.sync_ebay_stores(use_cached=use_cached)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_fb_stores(self, flat=False, do_sync=False, include_non_onboarded=False, use_cached=False):

        if self.is_subuser:
            stores = self.subuser_fb_stores.filter(is_active=True)
        else:
            stores = self.user.fbstore_set.filter(is_active=True)

        if not include_non_onboarded:
            stores = stores.exclude(creds__system_token__value=False)

        if do_sync and len(stores):
            # The function is defined in facebook_core.utils.py
            self.sync_fb_stores(use_cached=use_cached)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_google_stores(self, flat=False, do_sync=False, use_cached=False):
        if self.is_subuser:
            stores = self.subuser_google_stores.filter(is_active=True)
        else:
            stores = self.user.googlestore_set.filter(is_active=True)

        if do_sync and len(stores):
            # The function is defined in facebook_core.utils.py
            self.sync_google_stores(use_cached=use_cached)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_gear_stores(self, flat=False):
        if self.is_subuser:
            stores = self.subuser_gear_stores.filter(is_active=True)
        else:
            stores = self.user.gearbubblestore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_gkart_stores(self, flat=False):
        if self.is_subuser:
            stores = self.subuser_gkart_stores.filter(is_active=True)
        else:
            stores = self.user.groovekartstore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_bigcommerce_stores(self, flat=False):
        if self.is_subuser:
            stores = self.subuser_bigcommerce_stores.filter(is_active=True)
        else:
            stores = self.user.bigcommercestore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_fb_marketplace_stores(self, flat=False):
        if self.is_subuser:
            stores = self.subuser_fb_marketplace_stores.filter(is_active=True)
        else:
            stores = self.user.fbmarketplacestore_set.filter(is_active=True)

        if flat:
            stores = stores.values_list('id', flat=True)

        return stores

    def get_product_create_limit(self):
        if self.is_subuser:
            user = self.subuser_parent
        else:
            user = self.user
        plan = user.profile.get_plan()

        return plan.product_create_limit

    def get_installed_addon_titles(self):
        return list(self.addons.values_list('title', flat=True))

    def get_stores_count(self):
        return sum([
            self.get_shopify_stores().count(),
            self.get_chq_stores().count(),
            self.get_woo_stores().count(),
            self.get_ebay_stores().count(),
            self.get_fb_stores().count(),
            self.get_google_stores().count(),
            self.get_gear_stores().count(),
            self.get_gkart_stores().count(),
            self.get_bigcommerce_stores().count(),
            self.get_fb_marketplace_stores().count(),
        ])

    def get_suredone_stores_count(self):
        return sum([
            self.get_ebay_stores().count(),
            self.get_fb_stores().count(),
            self.get_google_stores().count(),
        ])

    def get_sd_accounts(self, flat=False):
        if self.is_subuser:
            accounts = self.subuser_sd_accounts.filter(is_active=True)
        else:
            accounts = self.user.suredoneaccount_set.filter(is_active=True)

        if flat:
            accounts = accounts.values_list('id', flat=True)

        return accounts

    def get_sub_users_count(self):
        if not self.is_subuser:
            return User.objects.filter(profile__subuser_parent=self.user).count()
        else:
            return None

    def get_new_alerts(self):
        return None

    @cached_property
    def get_perms(self):
        if self.plan.parent_plan:
            plan = self.plan.parent_plan
        else:
            plan = self.plan

        perms = list(plan.permissions.all().values_list('name', flat=True))
        for bundle in self.bundles.all():
            for i in bundle.permissions.values_list('name', flat=True):
                if i not in perms:
                    perms.append(i)

        if plan.support_addons:
            for addon in self.addons.all():
                for i in addon.permissions.values_list('name', flat=True):
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

    def supplies(self, item):
        if self.supplier is not None:
            return self.supplier == item.supplier
        return False

    def is_warehouse_account(self, item):
        if self.warehouse_account is not None:
            return self.warehouse_account == item.shipstation_account
        return True

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
        for name, val in list(data.items()):
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

    @property
    def is_subuser(self):
        return self.subuser_parent is not None

    def has_subuser_permission(self, codename, store=None):
        if not self.is_subuser:
            return True
        if store:
            store_model_name = store.__class__.__name__
            if store_model_name == 'ShopifyStore':
                return self.has_subuser_shopify_permission(codename, store)
            elif store_model_name == 'CommerceHQStore':
                return self.has_subuser_chq_permission(codename, store)
            elif store_model_name == 'WooStore':
                return self.has_subuser_woo_permission(codename, store)
            elif store_model_name == 'GearBubbleStore':
                return self.has_subuser_gear_permission(codename, store)
            elif store_model_name == 'GrooveKartStore':
                return self.has_subuser_gkart_permission(codename, store)
            elif store_model_name == 'BigCommerceStore':
                return self.has_subuser_bigcommerce_permission(codename, store)
            elif store_model_name == 'EbayStore':
                return self.has_subuser_ebay_permission(codename, store)
            elif store_model_name == 'FBStore':
                return self.has_subuser_fb_permission(codename, store)
            elif store_model_name == 'GoogleStore':
                return self.has_subuser_google_permission(codename, store)
            else:
                raise ValueError('Invalid store')

        # Permission is global
        return self.subuser_permissions.filter(codename=codename).exists()

    def has_subuser_shopify_permission(self, codename, store):
        if not self.subuser_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_permissions.filter(codename=codename, store=store).exists()

    def has_subuser_chq_permission(self, codename, store):
        if not self.subuser_chq_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_chq_permissions.filter(codename=codename, store=store).exists()

    def has_subuser_woo_permission(self, codename, store):
        if not self.subuser_woo_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_woo_permissions.filter(codename=codename, store=store).exists()

    def has_subuser_gear_permission(self, codename, store):
        if not self.subuser_gear_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_gear_permissions.filter(codename=codename, store=store).exists()

    def has_subuser_gkart_permission(self, codename, store):
        if not self.subuser_gkart_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_gkart_permissions.filter(codename=codename, store=store).exists()

    def has_subuser_bigcommerce_permission(self, codename, store):
        if not self.subuser_bigcommerce_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_bigcommerce_permissions.filter(codename=codename, store=store).exists()

    def has_subuser_ebay_permission(self, codename, store):
        if not self.subuser_ebay_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_ebay_permissions.filter(codename=codename, store=store).exists()

    def has_subuser_fb_permission(self, codename, store):
        if not self.subuser_fb_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_fb_permissions.filter(codename=codename, store=store).exists()

    def has_subuser_google_permission(self, codename, store):
        if not self.subuser_google_stores.filter(pk=store.id).exists():
            return False

        return self.subuser_google_permissions.filter(codename=codename, store=store).exists()

    def add_ip(self, ip):
        if not ip:
            return

        try:
            user_ips = json.loads(self.ips)
        except:
            user_ips = []

        if ip not in user_ips:
            user_ips.append(ip)

            self.ips = json.dumps(user_ips[-9:])  # Save last 9 Ips
            self.save()

    def from_shopify_app_store(self):
        return bool(self.shopify_app_store or self.get_config_value('shopify_app_store') or self.plan.payment_gateway == 'shopify')

    def get_current_shopify_subscription(self):
        for shopifysubscription in self.user.shopifysubscription_set.all():
            if shopifysubscription.plan and shopifysubscription.plan.id == self.plan.id:
                return shopifysubscription

    @cached_property
    def on_trial(self):
        cache_key = 'user_on_trial_{}'.format(self.user.id)
        on_trial = cache.get(cache_key)

        if on_trial is None:
            on_trial = False

            if self.plan.payment_gateway == 'shopify':
                subscription = self.get_current_shopify_subscription()
                on_trial = subscription.on_trial if subscription else False

            if self.plan.payment_gateway == 'stripe':
                on_trial = self.user.stripe_customer.on_trial

            cache.set(cache_key, on_trial, 60)

        return on_trial

    @cached_property
    def trial_days_left(self):
        cache_key = 'user_trial_days_left_{}'.format(self.user.id)
        trial_days_left = cache.get(cache_key)

        if trial_days_left is None:
            trial_days_left = 0

            if self.plan.payment_gateway == 'shopify':
                subscription = self.get_current_shopify_subscription()
                trial_days_left = subscription.trial_days_left if subscription else 0

            elif self.plan.payment_gateway == 'stripe':
                trial_days_left = self.user.stripe_customer.trial_days_left

            cache.set(cache_key, trial_days_left, 60)

        return trial_days_left

    def sync_tags(self):
        """ Send current user tags to Intercom and Baremetrics """
        from shopified_core.tasks import update_baremetrics_attributes, update_intercom_tags

        update_intercom_tags.apply_async(
            args=[self.user.email, 'user_tags', self.tags],
            expires=900)

        if settings.BAREMETRICS_TAGS_FIELD:
            update_baremetrics_attributes.apply_async(
                args=[self.user.email, settings.BAREMETRICS_TAGS_FIELD, self.tags],
                expires=900)

    def get_tags(self):
        """ Return user tags as a list"""
        tags = self.tags or ''
        return [i.strip() for i in tags.split(',')]

    def set_tags(self, tags):
        self.tags = ','.join(tags)
        self.save()

        self.sync_tags()

    def add_tags(self, tags):
        added_tags = []
        current_tags = self.get_tags()
        for tag in tags:
            if tag not in current_tags:
                added_tags.append(tag)
                current_tags.append(tag)

        self.tags = ','.join(current_tags)
        self.save()

        if added_tags:
            self.sync_tags()

    def remove_tags(self, tags):
        removed_tags = []
        current_tags = self.get_tags()
        for tag in tags:
            try:
                tag_index = current_tags.index(tag)
                removed_tags.append(current_tags.pop(tag_index))
            except ValueError:  # Index not found
                pass

        self.tags = ','.join(current_tags)
        self.save()

        if removed_tags:
            self.sync_tags()

    def get_auto_fulfill_limit(self):
        if self.is_subuser:
            user = self.subuser_parent
        else:
            user = self.user
        plan = user.profile.get_plan()
        auto_fulfill_limit = plan.auto_fulfill_limit

        if plan.auto_fulfill_limit != -1:
            # check addongs
            addons_auto_fulfill_limit = user.profile.addons.all().aggregate(Sum('auto_fulfill_limit'))['auto_fulfill_limit__sum'] or 0
            auto_fulfill_limit += addons_auto_fulfill_limit

            if user.get_config('_double_orders_limit'):
                auto_fulfill_limit *= 2

        return auto_fulfill_limit

    def get_surdone_orders_limit(self):
        if self.is_subuser:
            user = self.subuser_parent
        else:
            user = self.user
        plan = user.profile.get_plan()
        suredone_orders_limit = plan.suredone_orders_limit

        if plan.suredone_orders_limit != -1:
            # check addons
            addons_suredone_orders_limit = user.profile.addons.all().aggregate(Sum('suredone_orders_limit'))['suredone_orders_limit__sum'] or 0
            suredone_orders_limit += addons_suredone_orders_limit

            if user.get_config('_double_orders_limit'):
                suredone_orders_limit *= 2

        return suredone_orders_limit

    def get_orders_count(self, order_track):
        if self.is_subuser:
            user = self.subuser_parent
        else:
            user = self.user
        limit_check_key = 'orders_count_{}_{}'.format(order_track.__name__, user.id)

        if cache.get(limit_check_key) is None:
            month_start = arrow.utcnow().span('month')[0].datetime

            # This is used for Oberlo migration
            if user.get_config('auto_fulfill_limit_start'):
                auto_start = arrow.get(user.get_config('auto_fulfill_limit_start'))
                if auto_start > month_start:
                    month_start = auto_start

            orders_count = order_track.objects.filter(user=user, created_at__gte=month_start).count()

            cache.set(limit_check_key, orders_count, timeout=3600)
        else:
            orders_count = cache.get(limit_check_key)

        return orders_count

    def get_product_update_limit(self):
        if self.is_subuser:
            user = self.subuser_parent
        else:
            user = self.user
        plan = user.profile.get_plan()
        return plan.product_update_limit

    @property
    def is_black(self):
        return self.can('pls.use')

    @property
    def phone(self):
        return self.get_config_value('__phone', False)

    @property
    def use_new_navigation(self):
        return not any([
            self.get_config_value('revert_to_v2210311', True),
            self.plan.is_plod,
            self.is_black,
            self.dropified_private_label,
            self.private_label
        ])


class AddressBase(models.Model):
    class Meta:
        abstract = True

    name = models.CharField(max_length=100, blank=True, default='')
    address_line1 = models.CharField(max_length=255, blank=True, default='')
    address_line2 = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    zip_code = models.CharField(max_length=100, blank=True, default='')

    def vat_support(self):
        return False


class UserAddress(AddressBase):
    phone = models.CharField(max_length=100, blank=True, default='')

    def __str__(self):
        return f'<UserAddress: {self.id}>'


class UserCompany(AddressBase):
    vat = models.CharField(max_length=100, blank=True, default='')

    def vat_support(self):
        return True

    def __str__(self):
        return f'<UserCompany: {self.id}>'


class UserBlackSampleTracking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='samples')

    name = models.CharField(max_length=100, blank=True, default='')
    tracking_number = models.CharField(max_length=100, blank=True, default='')
    tracking_url = models.CharField(max_length=150, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<UserBlackSampleTracking: {self.id}>'


class SubuserPermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('ShopifyStore', blank=True, null=True, related_name='subuser_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserPermission: {self.id}>'


class SubuserCHQPermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('commercehq_core.CommerceHQStore', related_name='subuser_chq_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserCHQPermission: {self.id}>'


class SubuserWooPermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('woocommerce_core.WooStore', related_name='subuser_woo_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserCHQPermission: {self.id}>'


class SubuserGearPermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('gearbubble_core.GearBubbleStore', related_name='subuser_gear_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserGearPermission: {self.id}>'


class SubuserGKartPermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('groovekart_core.GrooveKartStore', related_name='subuser_gkart_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserGKartPermission: {self.id}>'


class SubuserGooglePermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('google_core.GoogleStore', related_name='subuser_google_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserGooglePermission: {self.id}>'


class SubuserBigCommercePermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('bigcommerce_core.BigCommerceStore', related_name='subuser_bigcommerce_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserBigCommercePermission: {self.id}>'


class SubuserEbayPermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('ebay_core.EbayStore', related_name='subuser_ebay_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserEbayPermission: {self.id}>'


class SubuserFBPermission(models.Model):
    codename = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    store = models.ForeignKey('facebook_core.FBStore', related_name='subuser_fb_permissions', on_delete=models.CASCADE)

    class Meta:
        ordering = 'pk',
        unique_together = 'codename', 'store'

    def __str__(self):
        return f'<SubuserFBPermission: {self.id}>'


class ShopifyStore(StoreBase):
    class Meta:
        ordering = ['list_index', '-created_at']

    api_url = models.CharField(max_length=512)
    title = models.CharField(max_length=512, blank=True, default='')

    # For OAuth App
    shop = models.CharField(max_length=512, blank=True, null=True)
    access_token = models.CharField(max_length=512, blank=True, null=True)
    scope = models.CharField(max_length=512, blank=True, null=True)
    primary_location = models.BigIntegerField(blank=True, null=True)
    dropified_location = models.BigIntegerField(blank=True, null=True)
    dropified_fulfillment_service = models.BigIntegerField(blank=True, null=True)

    is_active = models.BooleanField(default=True, db_index=True)
    store_hash = models.CharField(unique=True, default='', max_length=50, editable=False)
    version = models.IntegerField(default=1, choices=((1, 'Private App'), (2, 'Shopify App')), verbose_name='Store Version')

    info = models.TextField(null=True, blank=True)
    auto_fulfill = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    private_label = models.BooleanField(null=True, default=False, verbose_name='Using Private Label App')

    uninstall_reason = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    uninstalled_at = models.DateTimeField(null=True, blank=True)
    delete_request_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.store_hash:
            self.store_hash = get_random_string(32, 'abcdef0123456789')

        try:
            auto_fulfill = self.user.get_config('auto_shopify_fulfill', 'enable')

            if auto_fulfill and self.auto_fulfill != auto_fulfill:
                self.auto_fulfill = auto_fulfill

        except User.DoesNotExist:
            pass

        if not self.shop and self.api_url:
            self.shop = self.get_shop(full_domain=True)

        super(ShopifyStore, self).save(*args, **kwargs)

    def __str__(self):
        return self.title

    def need_reauthorization(self):
        return self.version == 1 or sorted(self.scope.split(',')) != sorted(settings.SHOPIFY_API_SCOPE)

    def get_link(self, page=None, api=False, version=SHOPIFY_API_VERSION):
        if api:
            raise NotImplementedError("Use ShoifyStore.api to get API links")

        url = re.findall(r'[^@\.]+\.myshopify\.com', self.api_url)[0]

        if page:
            url = url_join(f'https://{url}', page)
        else:
            url = f'https://{url}'

        return url

    def api(self, *pages, version=SHOPIFY_API_VERSION):
        ''' Get Shopify API link

        Return a Shopify API link with basic auth and the resources path
        Example usage:
            store.api('orders') => '/admin/api/{SHOPIFY_API_VERSION}/orders.json'
            store.api('orders', 1234567) => '/admin/api/{SHOPIFY_API_VERSION}/orders/1234567.json'

        Note that this examples return the same result:
            store.api('orders')
            store.api('orders.json')
            store.api('/admin/orders.json')
            store.api('admin/orders.json')
            store.api('admin', 'orders')
            store.api('admin', 'orders.json')

        Args:
            *pages: list or string to Shopify API resource
            version: Shoify API version to use (default: {SHOPIFY_API_VERSION})
        '''

        assert '2019' not in version

        url = re.findall(r'[^/]+@[^@\.]+\.myshopify\.com', self.api_url)[0]

        if len(pages) == 1 and type(pages[0]) is str and pages[0].startswith('https://'):
            pages = list(pages)
            pages[0] = pages[0].split('.myshopify.com').pop()

        page = url_join(*pages)

        page = re.sub(r'^/?admin/(api/[0-9-]+/)?', '', page)

        if '.json' not in page:
            page = f'{page}.json'

        url = url_join(f'https://{url}', 'admin', 'api', version, page)

        return url

    def graphql(self, query, variables=None):
        return requests.post(
            url=f'https://{self.shop}/admin/api/{SHOPIFY_API_VERSION}/graphql.json',
            headers={
                'X-Shopify-Access-Token': self.access_token,
            },
            json={
                'query': query,
                'variables': variables
            }
        ).json()

    @property
    def gql(self):
        return ShopifyGraphQL(self)

    def get_order(self, order_id):
        response = requests.get(url=self.api('orders', order_id))
        order = response.json()['order']

        from leadgalaxy.utils import shopify_customer_address
        get_config = self.user.models_user.get_config
        order['shipping_address'] = shopify_customer_address(
            order,
            german_umlauts=get_config('_use_german_umlauts', False),
            shipstation_fix=True
        )[1]

        return order

    def get_product(self, product_id, store):
        return ShopifyProduct.objects.all().get(shopify_id=product_id, store=store)

    def get_api_url(self, hide_keys=False):
        url = self.api_url

        if not url.startswith('http'):
            url = 'https://%s' % url

        if hide_keys:
            url = re.sub('[a-z0-9]*:[a-z0-9]+@', '*:*@', url)

        return url

    def get_api_credintals(self):
        api_key, api_secret = re.findall(r'(\w+)?:(\w+)', self.api_url).pop()

        return {
            'api_key': api_key,
            'api_secret': api_secret
        }

    def get_shop(self, full_domain=False):
        from leadgalaxy.utils import get_domain

        shop = get_domain(self.get_link(), full=True)

        return shop if full_domain else shop.split('.')[0]

    def update_token(self, token, shop=None, commit=True):
        if shop is None:
            shop = self.get_shop(full_domain=True)

        self.api_url = 'https://:{}@{}'.format(token['access_token'], shop)
        self.access_token = token['access_token']
        self.scope = '|'.join(token['scope'])
        self.version = 2

        if commit:
            self.save()

    def get_orders_count(self, status='open', fulfillment='unshipped', financial='any',
                         query='', all_orders=False, created_range=None, days=None):
        if all_orders:
            fulfillment = 'any'
            financial = 'any'
            status = 'any'
            query = ''

        params = {
            'status': status,
            'fulfillment_status': fulfillment,
            'financial_status': financial,
        }

        if query:
            params['ids'] = query

        if created_range and len(created_range):
            if created_range[0]:
                params['created_at_min'] = created_range[0]

            if created_range[1]:
                params['created_at_max'] = created_range[1]

        if days:
            params['created_at_min'] = arrow.utcnow().replace(days=-abs(days)).isoformat()

        try:
            return requests.get(
                url=self.api('orders/count'),
                params=params
            ).json().get('count', 0)
        except:
            capture_exception()
            return 0

    @property
    def shopify(self):
        import shopify
        session = shopify.Session(
            shop_url=self.shop,
            version=SHOPIFY_API_VERSION,
            token=self.get_api_credintals()['api_secret'])
        shopify.ShopifyResource.activate_session(session)

        return shopify

    @cached_property
    def get_info(self):
        rep = requests.get(url=self.api('shop'))
        rep = rep.json()

        if 'shop' in rep:
            return rep['shop']
        else:
            raise Exception(rep['errors'])

    def refresh_info(self, info=None, commit=True):
        if info is None:
            info = self.get_info

        if type(info) is dict:
            info = json.dumps(info)

        self.info = info

        if commit:
            self.save()

    def get_short_hash(self):
        return self.store_hash[:8] if self.store_hash else ''

    def is_synced(self):
        from shopify_orders.utils import is_store_synced
        return is_store_synced(self)

    def is_sync_enabled(self):
        from shopify_orders.utils import is_store_sync_enabled, is_store_synced
        return is_store_synced(self) and is_store_sync_enabled(self)

    def connected_count(self):
        return self.shopifyproduct_set.exclude(shopify_id=0).count()

    def saved_count(self):
        if len(self.user.profile.get_shopify_stores()) == 1:
            return self.user.shopifyproduct_set.filter(shopify_id=0).filter(Q(store__is_active=True) | Q(store=None)).count()
        else:
            return self.shopifyproduct_set.filter(shopify_id=0).count()

    def pending_orders(self):
        if self.user.get_config('_disable_pending_orders'):
            return None

        return self.shopifyorder_set.filter(closed_at=None, cancelled_at=None) \
                                    .filter(need_fulfillment__gt=0) \
                                    .filter(created_at__gte=arrow.now().replace(days=-30).datetime) \
                                    .count()

    def awaiting_tracking(self):
        if self.user.get_config('_disable_awaiting_tracking'):
            return None

        return self.shopifyordertrack_set.filter(hidden=False) \
                                         .filter(source_tracking='') \
                                         .filter(created_at__gte=arrow.now().replace(days=-30).datetime) \
                                         .filter(shopify_status='') \
                                         .exclude(source_status='FINISH') \
                                         .count()

    def pusher_channel(self):
        return 'shopify_{}'.format(self.get_short_hash())

    def pusher_trigger(self, event, data):
        if not settings.PUSHER_APP_ID:
            return

        pusher = Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET)

        try:
            pusher.trigger(self.pusher_channel(), event, data)
        except ValueError:
            pass

    def get_primary_location(self):
        if self.primary_location:
            return self.primary_location

        try:
            store_info = json.loads(self.info)
        except:
            store_info = None
        info = store_info or self.get_info

        if info.get('primary_location_id'):
            self.primary_location = info.get('primary_location_id')
            self.save()
            return self.primary_location

        response = requests.get(self.api('locations'))
        locations = response.json()['locations']
        primary_location = locations[0].get('id')

        return primary_location

    def get_dropified_location(self):
        if self.dropified_location:
            return self.dropified_location

        api_data = {
            "fulfillment_service": {
                "name": "Dropified",
                "callback_url": app_link("/webhooks/shopify/fulfillment"),
                "inventory_management": True,
                "permits_sku_sharing": True,
                "fulfillment_orders_opt_in": True,
                "tracking_support": True,
                "requires_shipping_method": True,
                "format": "json"
            }
        }

        rep = requests.post(
            url=self.api('fulfillment_services'),
            json=api_data
        )

        if rep.ok:
            self.dropified_fulfillment_service = rep.json()['fulfillment_service']['id']
            self.dropified_location = rep.json()['fulfillment_service']['location_id']
            self.save()

            return self.dropified_location
        else:
            if "You already have a location with this name" in rep.text:
                rep = requests.get(url=self.api('fulfillment_services'))
                rep.raise_for_status()

                for service in rep.json()['fulfillment_services']:
                    if service['name'] == 'Dropified':
                        rep = requests.put(
                            url=self.api('fulfillment_services', service['id']),
                            json=api_data
                        )

                        rep.raise_for_status()

                        self.dropified_fulfillment_service = service['id']
                        self.dropified_location = service['location_id']
                        self.save()

                        return self.dropified_location
            else:
                rep.raise_for_status()

    def get_locations(self, fulfillments_only=False, active_only=True):
        try:
            locations_key = 'stoe_locations_{}'.format(self.id)
            locations = cache.get(locations_key)
            if locations is None:

                rep = requests.get(self.api('locations'))
                rep.raise_for_status()

                locations = rep.json()['locations']

                cache.set(locations_key, locations, timeout=3600)

            if fulfillments_only:
                locations = [i for i in locations if i['legacy']]

            if active_only:
                locations = [i for i in locations if i['active']]

            return locations
        except:
            return []

    def get_location(self, name=None, location_id=None):
        locations = self.get_locations(fulfillments_only=True)

        if locations:
            for loc in locations:
                if name and name == loc['name']:
                    return loc
                elif location_id and location_id == loc['id']:
                    return loc

        if len(locations) == 1:
            if self.primary_location != locations[0]['id']:
                self.primary_location = locations[0]['id']
                self.save()

            return locations[0]

        return None

    def get_page_url(self, url_name):
        if url_name == 'orders_list':
            url_name = 'orders'
        return super().get_page_url(url_name)


class AccessToken(models.Model):
    class Meta:
        ordering = ['-created_at']

    token = models.CharField(max_length=512, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return f'<AccessToken: {self.id}>'

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = get_random_string(128)

        super().save(*args, **kwargs)


class ShopifyProduct(ProductBase):
    class Meta:
        ordering = ['-created_at']

    store = models.ForeignKey(ShopifyStore, blank=True, null=True, on_delete=models.CASCADE)

    original_data = models.TextField(default='', blank=True)
    original_data_key = models.CharField(max_length=32, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_excluded = models.BooleanField(null=True)

    shopify_id = models.BigIntegerField(default=0, null=True, blank=True, db_index=True)
    price_notification_id = models.IntegerField(default=0)

    parent_product = models.ForeignKey('ShopifyProduct', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Dupliacte of product')
    default_supplier = models.ForeignKey('ProductSupplier', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f'<ShopifyProduct: {self.id}>'

    def get_original_data(self):
        try:
            if self.original_data_key:
                data_store = using_store_db(DataStore).get(key=self.original_data_key)
                return data_store.data
            return getattr(self, 'original_data', '{}')
        except:
            pass

    def set_original_data(self, value, clear_original=False, commit=True):
        try:
            if self.original_data_key:
                data_store = using_store_db(DataStore).get(key=self.original_data_key)
                data_store.data = value
                data_store.save()
            else:
                while True:
                    data_key = hashlib.md5(get_random_string(32).encode()).hexdigest()

                    try:
                        using_store_db(DataStore).get(key=data_key)
                        continue  # Retry an other key

                    except DataStore.DoesNotExist:
                        # the key is unique
                        using_store_db(DataStore).create(key=data_key, data=value)

                        self.original_data_key = data_key

                        if clear_original:
                            self.original_data = ''

                        if commit:
                            self.save()

                        break
        except:
            pass

    def save(self, *args, **kwargs):
        if self.data and '\x00' in self.data:
            self.data = self.data.replace('\x00', '')

        data = json.loads(self.data)

        self.title = data.get('title', '')
        self.tags = data.get('tags', '')[:1024]
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

    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    @property
    def source_id(self):
        return self.shopify_id

    @source_id.setter
    def source_id(self, source_id):
        self.shopify_id = source_id

    @property
    def is_connected(self):
        return bool(self.get_shopify_id())

    @property
    def boards(self):
        return self.shopifyboard_set

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
        try:
            return json.loads(self.data)['images']
        except:
            return []

    def get_image(self):
        images = self.get_images()
        return images[0] if images else None

    def get_original_info(self, url=None):
        if not url:
            data = json.loads(self.data)
            url = data.get('original_url')

        if url:
            # Extract domain name
            try:
                domain = urlparse(url).hostname
            except:
                domain = None

            if domain is None:
                return domain

            for i in ['com', 'co.uk', 'org', 'net']:
                domain = domain.replace('.%s' % i, '')

            domain = domain.split('.')[-1]
            source = {
                'aliexpress': 'AliExpress',
                'ebay': 'eBay',
            }.get(domain.lower(), domain.title())

            return {
                'domain': domain,
                'source': source,
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
                info['url'] = 'http:{}'.format(info['url'])

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

    def set_variant_mapping(self, mapping, supplier=None, update=False, commit=True):
        if supplier is None:
            supplier = self.default_supplier

        if update:
            try:
                current = json.loads(supplier.variants_map)
            except:
                current = {}

            for k, v in list(mapping.items()):
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        if supplier:
            supplier.variants_map = mapping
            if commit:
                supplier.save()
        else:
            self.variants_map = mapping
            if commit:
                self.save()

    def get_variant_mapping(self, name=None, default=None, for_extension=False, supplier=None, mapping_supplier=False):
        mapping = {}

        if supplier is None:
            if mapping_supplier:
                supplier = self.get_supplier_for_variant(name)
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

        if for_extension and mapping:
            if name:
                if type(mapping) is str:
                    mapping = mapping.split(',')
            else:
                for k, v in list(mapping.items()):
                    m = str(v) if type(v) is int else v

                    try:
                        m = json.loads(v)
                    except:
                        if type(v) is str:
                            m = v.split(',')

                    mapping[k] = m

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

                    options = [{'title': a} for a in options]

                try:
                    if type(options) not in [list, dict]:
                        options = json.loads(options)

                        if type(options) is int:
                            options = str(options)
                except:
                    pass

                variants_map[str(v['id'])] = options
                seen_variants.append(str(v['id']))

            for k in list(variants_map.keys()):
                if k not in seen_variants:
                    del variants_map[k]

            all_mapping[str(supplier.id)] = variants_map

        return all_mapping

    def set_real_variant(self, deleted_id, real_id):
        config = self.get_config()
        mapping = config.get('real_variant_map', {})
        mapping[str(deleted_id)] = int(real_id)

        config['real_variant_map'] = mapping

        self.config = json.dumps(config, indent=4)
        self.save()

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

    def set_suppliers_mapping(self, mapping, commit=True):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.supplier_map = mapping

        if commit:
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

    def get_supplier_for_variant(self, variant_id):
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

    def set_shipping_mapping(self, mapping, update=True, commit=True):
        if update:
            try:
                current = json.loads(self.shipping_map)
            except:
                current = {}

            for k, v in list(mapping.items()):
                current[k] = v

            mapping = current

        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.shipping_map = mapping

        if commit:
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

        if data.get('weight_unit') == 'lbs':
            data['weight_unit'] = 'lb'

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)

    def get_data(self):
        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}
        return product_data

    def get_inventory_item_by_variant(self, variant_id, variant=None, ensure_tracking=True):
        if variant is None:
            response = requests.get(url=self.store.api('variants', variant_id))
            variant = response.json()['variant']

        if ensure_tracking and variant['inventory_management'] != 'shopify':
            requests.put(
                url=self.store.api('inventory_items', variant['inventory_item_id']),
                json={
                    "inventory_item": {
                        "id": variant['inventory_item_id'],
                        "tracked": True
                    }
                })

        return variant.get('inventory_item_id')

    def set_variant_quantity(self, quantity, variant_id=None, inventory_item_id=None, variant=None):
        if inventory_item_id is None:
            if variant_id is None:
                variant_id = variant['id']

            inventory_item_id = self.get_inventory_item_by_variant(variant_id, variant=variant)

        return requests.post(
            url=self.store.api('inventory_levels/set'),
            json={
                'location_id': self.store.get_dropified_location(),
                'inventory_item_id': inventory_item_id,
                'available': quantity,
            }
        )

    def get_variant_quantity(self, variant_id=None, inventory_item_id=None, variant=None):
        if inventory_item_id is None:
            if variant_id is None:
                variant_id = variant['id']

            inventory_item_id = self.get_inventory_item_by_variant(variant_id, variant=variant, ensure_tracking=False)

        response = requests.get(
            url=self.store.api('inventory_levels'),
            params={
                'inventory_item_ids': inventory_item_id,
                'location_ids': self.store.get_dropified_location()
            }
        )

        inventories = response.json()['inventory_levels']

        inventory = {}
        if len(inventories):
            inventory = inventories[0]

        return inventory.get('available', 0)

    def get_master_variants_map(self):
        try:
            return json.loads(self.master_variants_map)
        except:
            return {}

    def set_master_variants_map(self, mapping):
        if type(mapping) is not str:
            mapping = json.dumps(mapping)

        self.master_variants_map = mapping
        self.save()


class ProductSupplier(SupplierBase):
    store = models.ForeignKey(ShopifyStore, null=True, on_delete=models.CASCADE)
    product = models.ForeignKey(ShopifyProduct, on_delete=models.CASCADE)

    product_url = models.CharField(max_length=512, null=True, blank=True)
    supplier_name = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    supplier_url = models.CharField(max_length=512, null=True, blank=True)
    shipping_method = models.CharField(max_length=512, null=True, blank=True)
    variants_map = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    source_id = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<ProductSupplier: {self.id}>'

    def get_source_id(self):
        try:
            if self.is_aliexpress:
                return int(re.findall('[/_]([0-9]+).html', self.product_url)[0])
            elif self.is_alibaba:
                return int(re.findall('[/_]([0-9]+)(?:.html|-[0-9]+)', self.product_url)[0])
            elif self.is_ebay:
                return int(re.findall(r'ebay\.[^/]+\/itm\/(?:[^/]+\/)?([0-9]+)', self.product_url)[0])
            elif self.is_dropified_print:
                return int(re.findall(r'print-on-demand.+?([0-9]+)', self.product_url)[0])
            elif self.is_pls:
                return self.get_user_supplement_id()
            elif self.is_logistics:
                return int(re.findall(r'logistics/\S+/([0-9]+)', self.product_url)[0])
        except:
            return None

    def get_store_id(self):
        try:
            if self.is_aliexpress:
                return int(re.findall('/([0-9]+)', self.supplier_url).pop())
        except:
            return None

    def short_product_url(self):
        source_id = self.get_source_id()
        if source_id:
            if self.is_aliexpress:
                return 'https://www.aliexpress.com/item/{}.html'.format(source_id)
            if self.is_ebay:
                return 'https://www.ebay.com/itm/{}'.format(source_id)

        return self.product_url

    def get_affiliate_link(self):
        if self.is_ebay:
            from leadgalaxy.utils import get_ebay_affiliate_url
            return get_ebay_affiliate_url(self.short_product_url())
        else:
            return self.short_product_url()

    def support_auto_fulfill(self):
        """
        Return True if this supplier support auto fulfill using the extension
        Currently Aliexpress and eBay (US) support that
        """

        return self.is_aliexpress or self.is_ebay_us

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

            name = 'Supplier {}#{}'.format(self.supplier_type(), supplier_idx)

        return name

    @property
    def is_aliexpress(self):
        return self.supplier_type() == 'aliexpress'

    @property
    def is_ebay(self):
        return self.supplier_type() == 'ebay'

    @property
    def is_ebay_us(self):
        try:
            return bool(re.search(r'ebay\.(com|co.uk|com.au|de|fr|ca)', get_domain(self.product_url, full=True)))
        except:
            return False

    def save(self, *args, **kwargs):
        if self.source_id != self.get_source_id():
            self.source_id = self.get_source_id()
        if self.is_default:
            try:
                if not settings.DEBUG:
                    monitor_product(self.product)
            except:
                pass

        super(ProductSupplier, self).save(*args, **kwargs)


class ShopifyProductImage(models.Model):
    product = models.BigIntegerField(verbose_name="Shopify Product ID")
    variant = models.BigIntegerField(default=0, verbose_name="Shopify Product ID")
    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE)

    image = models.CharField(max_length=512, blank=True, default='')

    def __str__(self):
        return f'<ShopifyProductImage: {self.id}>'


class ShopifyOrderTrack(OrderTrackBase):
    store = models.ForeignKey(ShopifyStore, null=True, on_delete=models.CASCADE)
    shopify_status = models.CharField(max_length=128, blank=True, null=True, default='',
                                      verbose_name="Shopify Fulfillment Status")

    source_tracking = models.CharField(max_length=128, blank=True, default='', db_index=True, verbose_name="Source Tracking Number")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Submission date')

    def __str__(self):
        return f'<ShopifyOrderTrack: {self.id} | {self.order_id} - {self.line_id}>'

    def get_shopify_link(self):
        return self.store.get_link('/admin/orders/{}'.format(self.order_id))


class ShopifyBoard(BoardBase):
    products = models.ManyToManyField(ShopifyProduct, blank=True)

    def __str__(self):
        return f'<ShopifyBoard: {self.id} | {self.title}>'

    def saved_count(self, request=None):
        # Filter non-connected products
        products = self.products.filter(shopify_id=0)

        if request and request.user.is_subuser:
            # If it's a sub user, only show him products in stores he have access to
            products = products.filter(Q(store__in=request.user.profile.get_shopify_stores()) | Q(store=None))
        else:
            # Show the owner product linked to active stores and products with store set to None
            products = products.filter(Q(store__is_active=True) | Q(store=None))

        return products.count()

    def connected_count(self, request=None):
        # Only get products linked to a Shopify product and with an active store
        products = self.products.filter(store__is_active=True).exclude(shopify_id=0)

        if request and request.user.is_subuser:
            products = products.filter(store__in=request.user.profile.get_shopify_stores())

        return products.count()


class ShopifyWebhook(models.Model):
    class Meta:
        ordering = ['-created_at']
        unique_together = ('store', 'topic')

    store = models.ForeignKey(ShopifyStore, on_delete=models.CASCADE)
    topic = models.CharField(max_length=64)
    token = models.CharField(max_length=64)
    shopify_id = models.BigIntegerField(default=0, verbose_name='Webhook Shopify ID')
    call_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<ShopifyWebhook: {self.id}>'

    def detach(self):
        """ Remove the webhook from Shopify """

        if not self.shopify_id:
            return

        endpoint = self.store.api('webhooks', self.shopify_id)
        try:
            requests.delete(endpoint)
        except Exception as e:
            print('WEBHOOK: detach excption', repr(e))
            return None


class AppPermissionTag(models.Model):
    name = models.CharField(max_length=128)
    slug = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True, default='')

    def __str__(self):
        return self.name

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
        }


class AppPermission(models.Model):
    name = models.CharField(max_length=512, verbose_name="Permission")
    description = models.CharField(max_length=512, blank=True, default='', verbose_name="Permission Description")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")
    image_url = models.CharField(max_length=512, blank=True, null=True, verbose_name="Image URL")

    tags = models.ManyToManyField(AppPermissionTag, blank=True)

    def __str__(self):
        if self.description:
            desc = self.description.split('|')[0].strip()
            perm_type = self.description.split('|').pop().strip() if '|' in self.description else ''
            if perm_type:
                return f'{desc} ({perm_type} {self.name})'
            else:
                return f'{desc} ({self.name})'
        else:
            return self.name

    def add_tag(self, tag):
        if isinstance(tag, str):
            tag, created = AppPermissionTag.objects.get_or_create(name=tag)
        self.tags.add(tag)

    def remove_tag(self, tag):
        if isinstance(tag, str):
            tag = AppPermissionTag.objects.get(name=tag)
        self.tags.remove(tag)

    def get_images(self):
        return self.image_url.split(',') if self.image_url else []

    def add_image(self, url):
        images = self.get_images()
        images.append(url)
        self.image_url = ','.join(images)

    def to_json(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'notes': self.notes,
            'image_url': self.image_url,
            'images': self.image_url.split(',') if self.image_url else [],
            'tags': [t.to_json() for t in self.tags.all()]
        }


class ClippingMagicPlan(models.Model):
    allowed_credits = models.IntegerField(default=0)
    amount = models.IntegerField(default=0, verbose_name='In USD')

    def __str__(self):

        return f'<ClippingMagicPlan: {self.id} | {self.allowed_credits} / {self.amount}>'


class ClippingMagic(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.OneToOneField(User, related_name='clippingmagic', on_delete=models.CASCADE)

    remaining_credits = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return f'<ClippingMagic: {self.id} | {self.remaining_credits} Credits>'


class CaptchaCreditPlan(models.Model):
    allowed_credits = models.IntegerField(default=0)
    amount = models.IntegerField(default=0, verbose_name='In USD')

    def __str__(self):
        return f'<CaptchaCreditPlan: {self.id} | {self.allowed_credits}>'


class CaptchaCredit(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.OneToOneField(User, related_name='captchacredit', on_delete=models.CASCADE)

    remaining_credits = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return f'<CaptchaCredit: {self.id} | {self.remaining_credits} Credits>'


class GroupPlan(models.Model):
    class Meta:
        ordering = ['title']

    title = models.CharField(max_length=512, blank=True, default='', verbose_name="Plan Title")
    slug = models.SlugField(unique=True, max_length=512, verbose_name="Plan Slug")
    register_hash = models.CharField(unique=True, max_length=50, editable=False)

    hubspot_title = models.CharField(max_length=512, blank=True, default='')

    stores = models.IntegerField(default=0, verbose_name="Stores Limit")
    suredone_stores = models.IntegerField(default=0, verbose_name="SureDone Channels Limit")
    products = models.IntegerField(default=0, verbose_name="Products Limit")
    boards = models.IntegerField(default=0, verbose_name="Boards Limit")
    unique_supplements = models.IntegerField(default=0, verbose_name="Unique Supplements Limit")
    user_supplements = models.IntegerField(default=0, verbose_name="User Supplements Limit")
    label_upload_limit = models.IntegerField(default=-1, verbose_name="Label Upload Limit per month")
    sub_users_limit = models.IntegerField(default=-1, verbose_name='Sub Users Limit')

    extra_stores = models.BooleanField(default=True, verbose_name='Support adding extra stores')
    extra_store_cost = models.DecimalField(decimal_places=2, max_digits=9, null=True, default=27.00,
                                           verbose_name='Extra store cost per store(in USD)')
    extra_subusers = models.BooleanField(default=True, verbose_name='Support adding extra sub users')
    extra_subuser_cost = models.DecimalField(decimal_places=2, max_digits=9, null=True, default=0.00,
                                             verbose_name='Extra sub user cost per user(in USD)')
    auto_fulfill_limit = models.IntegerField(default=-1, verbose_name="Auto Fulfill Limit")
    product_create_limit = models.IntegerField(default=10000, verbose_name="Suredone Products Create Limit")
    product_update_limit = models.IntegerField(default=10000, verbose_name="Suredone Product Update Limit")
    suredone_orders_limit = models.IntegerField(default=-1, verbose_name="Suredone Orders Limit")

    support_addons = models.BooleanField(default=False)
    single_charge = models.BooleanField(default=False)
    sales_fee_config = models.ForeignKey('fulfilment_fee.SalesFeeConfig', blank=True, null=True, on_delete=models.SET_NULL)

    badge_image = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='', verbose_name='Plan name visible to users')
    notes = models.TextField(null=True, blank=True, verbose_name='Admin Notes')
    features = models.TextField(null=True, blank=True, verbose_name='Features List')
    monthly_price = models.DecimalField(decimal_places=2, max_digits=9, null=True, blank=True, verbose_name='Monthly Price(in USD)')
    free_plan = models.BooleanField(default=True)
    trial_days = models.IntegerField(default=0)

    plan_description = models.CharField(max_length=512, blank=True, null=True, verbose_name='Plan description in in Plans Page')
    dashboard_description = models.CharField(max_length=512, blank=True, null=True, verbose_name='Plan description on dashboard page')
    price_info = models.CharField(max_length=512, blank=True, null=True, verbose_name='Price info in Plans Page')
    retail_price_info = models.CharField(max_length=512, blank=True, null=True, verbose_name='Retail Price info in Plans Page')
    show_stores_count = models.BooleanField(default=True)
    show_fulfillment_fee = models.BooleanField(default=True)

    default_plan = models.IntegerField(default=0, choices=YES_NO_CHOICES)
    show_in_plod_app = models.IntegerField(default=0, choices=PLOD_SHOW_CHOICES, verbose_name='Show in PLoD App Listing')
    private_label = models.BooleanField(default=False, verbose_name='Private Label Plan')

    permissions = models.ManyToManyField(AppPermission, blank=True)

    goals = models.ManyToManyField('goals.Goal', related_name='plans', blank=True)

    payment_gateway = models.CharField(max_length=25, choices=PLAN_PAYMENT_GATEWAY, default=PLAN_PAYMENT_GATEWAY[0][0])
    payment_interval = models.CharField(max_length=25, choices=PLAN_PAYMENT_TYPE, default='')

    revision = models.CharField(max_length=128, blank=True, null=True)
    hidden = models.BooleanField(default=False, verbose_name='Hidden from users')
    locked = models.BooleanField(default=False, verbose_name='Disable Direct Subscription')

    parent_plan = models.ForeignKey('GroupPlan', null=True, on_delete=models.SET_NULL, blank=True, verbose_name='Use permissions from selected plan')

    def __str__(self):
        return f'{self.title} | {self.slug} | {self.id}'

    def save(self, *args, **kwargs):
        if not self.register_hash:
            self.register_hash = get_random_string(32, 'abcdef0123456789')

        super(GroupPlan, self).save(*args, **kwargs)

    def permissions_count(self):
        if self.parent_plan:
            return f'{self.parent_plan.permissions.count()} (From: {self.parent_plan.id})'
        else:
            return f'{self.permissions.count()}'

    def get_description(self):
        if self.plan_description:
            return self.plan_description

        interval = 'year' if self.payment_interval == 'yearly' else 'month'
        desc = self.description if self.description else self.title

        if self.is_stripe():
            desc = '{} ($ {:0.2f}/{})'.format(desc, self.stripe_plan.amount, interval)

        elif self.monthly_price:
            pricing = float(self.monthly_price) * 12.0 if self.payment_interval == 'yearly' else self.monthly_price
            desc = '{} ($ {:0.2f}/{})'.format(desc, pricing, interval)

        elif self.payment_interval == 'lifetime' and 'lifetime' not in desc.lower():
            desc = '{} (Lifetime)'.format(desc)

        return desc

    def get_price(self):

        interval = 'year' if self.payment_interval == 'yearly' else 'month'

        desc = ''
        if self.is_stripe():
            desc = '${:0.2f}/{}'.format(self.stripe_plan.amount, interval)

        elif (not self.monthly_price and self.monthly_price is not None) or self.is_free:
            desc = 'Inactive'

        elif self.monthly_price:
            pricing = float(self.monthly_price) * 12.0 if self.payment_interval == 'yearly' else self.monthly_price
            desc = '${:0.2f}/{}'.format(pricing, interval)

        elif self.payment_interval == 'lifetime':
            desc = 'Lifetime'

        return desc

    def get_total_cost(self):
        if self.payment_interval == 'yearly' and self.monthly_price:
            return float(self.monthly_price) * 12.0

        return self.monthly_price or 0

    def import_stores(self):
        ''' Return Stores this allow importing products from '''
        if self.parent_plan:
            permissions = self.parent_plan.permissions
        else:
            permissions = self.permissions
        stores = []
        for i in permissions.all():
            if i.name.endswith('_import.use') and 'pinterest' not in i.name:
                name = i.name.split('_')[0]
                stores.append(name.title())

        return stores

    def have_feature(self, perm_name):
        permission = AppPermission.objects.filter(name__iexact=perm_name)
        return permission and permission.groupplan_set.filter(id=permission.id).exists()

    def is_stripe(self):
        try:
            return self.payment_gateway == 'stripe' and bool(self.stripe_plan.stripe_id)
        except:
            return False

    def is_shopify(self):
        return self.payment_gateway == 'shopify'

    @property
    def is_paused(self):
        return self.slug in ['paused-plan', 'paused-plan-shopify']

    @property
    def is_free(self):
        return self.slug in ['free-stripe-plan', 'free-plan', 'shopify-free-plan'] or self.is_startup

    @property
    def is_lifetime_free(self):
        return self.slug in [
            'plod-lifetime-free-shopify',
            'plod-lifetime-free',
            'build-lifetime-free-shopify',
            'build-lifetime-free',
        ]

    @property
    def is_lifetime(self):
        return 'lifetime' in self.slug

    @property
    def is_active_free(self):
        # Free plans with access to features paying fee charges
        return self.slug in ['free-import-shopify', 'free-import-stripe']

    @property
    def is_lite(self):
        return self.slug in ['lite-stripe-plan', 'lite-plan']

    @property
    def is_startup(self):
        return self.slug in ['startup', 'startup-shopify', 'starter', 'starter-shopify']

    @property
    def is_upgradable(self):
        """ For plans that can be upgraded to a better version """
        return self.slug in ['builder', 'builder-yearly', 'builder-shopify', 'builder-yearly-shopify']

    @property
    def large_badge_image(self):
        return self.badge_image.replace('_small.', '.')

    @property
    def is_basic_import(self):
        return self.slug in ['import-yearly-shopify', 'import-monthly-shopify', 'import-yearly', 'import-monthly']

    @property
    def is_private_label(self):
        return self.slug in ['new-plod-yearly-shopify', 'new-plod-monthly-shopify', 'new-plod-yearly', 'new-plod-monthly']

    @property
    def is_black(self):
        return self.slug in ['supplements-premier-black-year', 'supplements-premier-black',
                             'new-black-yearly-shopify', 'new-black-monthly-shopify', 'new-black-yearly',
                             'new-black-monthly', 'black-yearly-webinar', 'dropified-black-affiliates',
                             'black-yearly-lifetime', 'black-m onthly', 'black-3-payments', 'black-yearly']

    @property
    def has_installments(self):
        return self.slug in [
            'build-lifetime-monthly-shopify',
            'build-lifetime-monthly',
            'plod-lifetime-monthly-shopify',
            'plod-lifetime-monthly',
        ]

    @property
    def is_build(self):
        return self.slug in ['build-yearly-shopify', 'build-monthly-shopify', 'build-yearly', 'build-monthly']

    @property
    def is_plod(self):
        return 'plod' in self.slug

    @property
    def is_research(self):
        return self.slug in ['research-shopify', 'research-free']

    def get_internal_plan(self):
        if self.slug in ['build-lifetime-monthly', 'build-lifetime-yearly']:
            return GroupPlan.objects.get(slug='build-lifetime-free')
        elif self.slug in ['plod-lifetime-monthly', 'plod-lifetime-yearly']:
            return GroupPlan.objects.get(slug='plod-lifetime-free')


class GroupPlanChangeLog(models.Model):
    user = models.OneToOneField(User, related_name='plan_change_log', on_delete=models.CASCADE)
    plan = models.ForeignKey(GroupPlan, null=True, on_delete=models.CASCADE)
    previous_plan = models.ForeignKey(GroupPlan, null=True, related_name='previous_plan', on_delete=models.CASCADE)

    changed_at = models.DateTimeField(null=True, blank=True, verbose_name='When Plan Changed')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<GroupPlanChangeLog: {self.id}>'


class FeatureBundle(models.Model):
    title = models.CharField(max_length=512, verbose_name="Bundle Title")
    slug = models.SlugField(unique=True, max_length=512, verbose_name="Bundle Slug")
    register_hash = models.CharField(unique=True, max_length=50, editable=False)
    description = models.CharField(max_length=512, blank=True, default='')
    hidden_from_user = models.BooleanField(default=False, verbose_name='Hide in User Profile')

    permissions = models.ManyToManyField(AppPermission, blank=True)

    def __str__(self):
        return f'Bundle: {self.title}'

    def save(self, *args, **kwargs):
        if not self.register_hash:
            self.register_hash = get_random_string(32, 'abcdef0123456789')

        super(FeatureBundle, self).save(*args, **kwargs)

    def permissions_count(self):
        return self.permissions.count()

    def get_description(self):
        return self.description if self.description else self.title


class UserUpload(UserUploadBase):
    product = models.ForeignKey(ShopifyProduct, null=True, on_delete=models.CASCADE)


class PlanRegistration(models.Model):
    class Meta:
        ordering = ['-created_at']

    plan = models.ForeignKey(GroupPlan, blank=True, null=True, on_delete=models.SET_NULL, verbose_name='Purchased Plan')
    bundle = models.ForeignKey(FeatureBundle, blank=True, null=True, on_delete=models.SET_NULL, verbose_name='Purchased Bundle')

    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    sender = models.ForeignKey(User, blank=True, null=True, related_name='sender', verbose_name='Plan Generated By', on_delete=models.CASCADE)
    email = models.CharField(blank=True, default='', max_length=120)
    register_hash = models.CharField(max_length=40, unique=True, editable=False)
    data = models.TextField(blank=True, default='')
    expired = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        desc = f'<PlanRegistration: {self.id}>'

        if self.plan:
            desc = f'Plan: {self.plan.title}'
        elif self.bundle:
            desc = f'Bundle: {self.bundle.title}'

        return desc

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


class AccountRegistration(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)
    register_hash = models.TextField(unique=True, editable=False)
    expired = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'AccountRegistration: {self.user.email}'

    def save(self, *args, **kwargs):
        if not self.register_hash:
            self.register_hash = get_random_string(64)

        super().save(*args, **kwargs)


class PlanPayment(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    fullname = models.CharField(blank=True, max_length=120)
    email = models.CharField(blank=True, max_length=120)
    provider = models.CharField(max_length=50)
    payment_id = models.CharField(max_length=120)
    transaction_type = models.CharField(blank=True, max_length=32)
    data = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'<PlanPayment: {self.id}>'


class DescriptionTemplate(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return f'<DescriptionTemplate: {self.id}>'


class PriceMarkupRule(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, null=True, blank=True)
    min_price = models.FloatField(default=0.0)
    max_price = models.FloatField(default=0.0)
    markup_value = models.FloatField(default=0.0, null=True)
    markup_compare_value = models.FloatField(default=0.0, null=True)
    markup_type = models.CharField(max_length=25, choices=PRICE_MARKUP_TYPES, default=PRICE_MARKUP_TYPES[0][0])

    def __str__(self):
        return f'<PriceMarkupRule: {self.id}>'

    def save(self, *args, **kwargs):
        name = '{} for prices from {:0.2f} to {:0.2f}'.format(self.get_markup_type_display(), self.min_price, self.max_price)

        if name != self.name:
            self.name = name

        super(PriceMarkupRule, self).save(*args, **kwargs)


class AdminEvent(models.Model):
    class Meta:
        ordering = ['-created_at']

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    target_user = models.ForeignKey(User, null=True, related_name='target_user', on_delete=models.CASCADE)
    event_type = models.CharField(max_length=30, blank=True, null=True)
    data = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'<AdminEvent: {self.id}>'


class DashboardVideo(models.Model):
    STORE_TYPES = (
        ('shopify', 'Shopify'),
        ('chq', 'CommerceHQ'),
        ('woo', 'WooCommerce'),
        ('gkart', 'GrooveKart'),
        ('bigcommerce', 'BigCommerce'),
    )

    url = models.TextField()
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    plans = models.ManyToManyField('GroupPlan', blank=True)
    store_type = models.CharField(max_length=50, default='shopify', choices=STORE_TYPES)
    display_order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f'<DashboardVideo: {self.id}>'

    class Meta:
        ordering = 'display_order',


@add_to_class(User, 'get_first_name')
def user_first_name(self):
    return self.first_name.title() if self.first_name else self.username


@add_to_class(User, 'get_access_token')
def user_get_access_token(self):
    try:
        access_token = AccessToken.objects.filter(user=self).latest('created_at')
    except:
        access_token = AccessToken(user=self)
        access_token.save()

    return access_token.token


@add_to_class(User, 'get_jwt_access_token')
def user_get_jwt_access_token(self):
    from shopified_core.utils import jwt_encode
    return jwt_encode({'id': self.id})


@add_to_class(User, 'can')
def user_can(self, perms, store_id=None):
    return self.profile.can(perms, store_id)


@add_to_class(User, 'supplies')
def supplies(self, item):
    return self.profile.supplies(item)


@add_to_class(User, 'is_warehouse_account')
def is_warehouse_account(self, item):
    return self.profile.is_warehouse_account(item)


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


@add_to_class(User, 'have_stripe_billing')
def user_have_stripe_billing(self):
    try:
        return bool(self.stripe_customer and self.stripe_customer.customer_id)
    except:
        return False


@add_to_class(User, 'is_recurring_customer')
def user_recurring_customer(self):
    try:
        return self.profile.plan.is_stripe()
    except:
        return False


@add_to_class(User, 'have_billing_info')
def user_have_billing_info(self):
    try:
        return bool(self.stripe_customer.source)
    except:
        return False


@add_to_class(User, 'can_trial')
def user_can_trial(self):
    if self.profile.from_shopify_app_store():
        return self.profile.get_config_value('_can_trial', True)

    try:
        return self.stripe_customer.can_trial
    except User.stripe_customer.RelatedObjectDoesNotExist:
        # If the customer object is not created yet, that mean the user didn't chose a Stripe plan yet
        return True


def user_is_subsuser(self):
    return self.profile.is_subuser


def user_models_user(self):
    if not self.profile.is_subuser:
        return self
    else:
        return self.profile.subuser_parent


User.add_to_class("is_subuser", property(user_is_subsuser))
User.add_to_class("models_user", property(user_models_user))
