"""
Django settings for app project, on Heroku. Fore more info, see:
https://github.com/heroku/heroku-django-template

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""


import os
import dj_database_url
import warnings

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))

SECRET_KEY = 'i+acxn5(akgsn!sr4^qgf(^m&*@+g1@u^t@=8s@axc41ml*f=s'

API_SECRECT_KEY = os.environ.get('API_SECRECT_KEY', 'TEST')
ENCRYPTION_SECRECT_KEY = os.environ.get('ENCRYPTION_SECRECT_KEY', 'TEST')
SSO_SECRET_KEY = os.environ.get('SSO_SECRET_KEY', 'TEST')

DEBUG = (os.environ.get('DEBUG_APP') == 'TRUE')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

APP_DOMAIN = os.environ.get('APP_DOMAIN', 'app.dropified.com')
APP_URL = os.environ.get('APP_URL', 'https://{}'.format(APP_DOMAIN))

# Application definition

INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_hooks',

    'raven.contrib.django.raven_compat',
    'widget_tweaks',
    'hijack',
    'compat',
    'compressor',
    'storages',
    'django_extensions',
    'test_without_migrations',
    'last_seen',
    'polymorphic',
    'adminsortable2',

    'article',
    'home',
    'leadgalaxy',
    'shopified_core',
    'shopify_oauth',
    'shopify_orders',
    'stripe_subscription',
    'shopify_subscription',
    'product_feed',
    'data_store',
    'product_alerts',
    'analytic_events',
    'order_exports',
    'order_imports',
    'profit_dashboard',
    'profits',
    'subusers',
    'tapfiliate',
    'youtube_ads',
    'sso_core',
    'goals',
    'metrics',

    'commercehq_core',
    'woocommerce_core',
    'gearbubble_core',
    'groovekart_core',
    'zapier_core',
    'phone_automation',
    'funnels',
    'aliextractor'
)

MIDDLEWARE = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'hijack.middleware.HijackRemoteUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'last_seen.middleware.LastSeenMiddleware',
    'leadgalaxy.utils.UserIpSaverMiddleware',
    'leadgalaxy.utils.TimezoneMiddleware',
    'leadgalaxy.utils.UserEmailEncodeMiddleware',
)

ROOT_URLCONF = 'app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'home.context_processors.all_stores',
                'article.context_processors.sidebarlinks',
                'leadgalaxy.context_processors.extra_bundles',
                'leadgalaxy.context_processors.extension_release',
                'leadgalaxy.context_processors.intercom',
                'leadgalaxy.context_processors.facebook_pixel',
                'leadgalaxy.context_processors.store_limits_check',
                'subusers.context_processors.template_config',
                'analytic_events.context_processors.analytic_events',
                'leadgalaxy.context_processors.tapafilate_conversaion',
            ],
        },
    },
]

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
)

WSGI_APPLICATION = 'app.wsgi.application'

DROPIFIED_API = {
    'all': 'shopified_core.api.ShopifiedApi',
    'shopify': 'leadgalaxy.api.ShopifyStoreApi',
    'chq': 'commercehq_core.api.CHQStoreApi',
    'gear': 'gearbubble_core.api.GearBubbleApi',
    'woo': 'woocommerce_core.api.WooStoreApi',
    'gkart': 'groovekart_core.api.GrooveKartApi',
    'tubehunt': 'youtube_ads.api.TubeHuntApi',
    'subusers': 'subusers.api.SubusersApi',
    'goals': 'goals.api.GoalsApi',
    'profits': 'profits.api.ProfitsApi',
    'metrics': 'metrics.api.MetricsApi',
}

# Database

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    },
}

DATABASE_STATEMENT_TIMEOUT = os.environ.get('DATABASE_STATEMENT_TIMEOUT')
CELERY_STATEMENT_TIMEOUT = os.environ.get('CELERY_STATEMENT_TIMEOUT')
COMMAND_STATEMENT_TIMEOUT = os.environ.get('COMMAND_STATEMENT_TIMEOUT')

# Ignore psycopg2-binary and urllib3 warnings
warnings.filterwarnings('ignore', module='psycopg2')
warnings.filterwarnings('ignore', module='urllib3', message='Unverified HTTPS request')

# Cache
REDISCLOUD_URL = os.environ['REDISCLOUD_URL']
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "{0}/0".format(os.environ.get('REDISCLOUD_CACHE', REDISCLOUD_URL)),
    },
    "orders": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "{0}/0".format(os.environ.get('REDISCLOUD_ORDERS', REDISCLOUD_URL)),
    }
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Parse database configuration from $DATABASE_URL
if os.environ.get('DATABASE_URL'):
    DATABASES['default'] = dj_database_url.config()

STORE_DATABASE = None
if os.environ.get('DATA_STORE_DATABASE_URL'):
    store_db_url = os.environ['DATA_STORE_DATABASE_URL']
    if os.environ.get(store_db_url):
        # Database URL is stored in an other env. variable
        store_db_url = os.environ[store_db_url]

    STORE_DATABASE = 'store_db'
    DATABASES[STORE_DATABASE] = dj_database_url.parse(store_db_url)
    DATABASES[STORE_DATABASE]['ENGINE'] = 'django_postgrespool'

READ_REPLICA = None
if os.environ.get('REPLICA_DATABASE_URL'):
    replica_url = os.environ['REPLICA_DATABASE_URL']
    if os.environ.get(replica_url):
        # Database URL is stored in an other env. variable
        replica_url = os.environ[replica_url]

    READ_REPLICA = 'replica'
    DATABASES[READ_REPLICA] = dj_database_url.parse(replica_url)

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ('HTTP_X_PROXY_PROTOCOL', 'https')

SECURE_SSL_REDIRECT = not DEBUG and not os.environ.get('DISABLE_SSL_REDIRECT')
SECURE_REDIRECT_EXEMPT = [
    '^webhook/',
    '^marketing/feeds/',
]

STATIC_ROOT = 'staticfiles'
STATIC_URL = '/static/'

STATICFILES_DIRS = (
    os.path.join(BASE_DIR, 'app/static'),
)

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = 'http://localhost/'

HIJACK_LOGIN_REDIRECT_URL = '/'
HIJACK_LOGOUT_REDIRECT_URL = '/'
HIJACK_DISPLAY_ADMIN_BUTTON = False
HIJACK_USE_BOOTSTRAP = True
HIJACK_ALLOW_GET_REQUESTS = True

EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_HOST_USER = os.environ.get('SENDGRID_USERNAME')
EMAIL_HOST_PASSWORD = os.environ.get('SENDGRID_PASSWORD')
EMAIL_PORT = 587
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = "support@dropified.com"

if not EMAIL_HOST_USER and DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


DATA_UPLOAD_MAX_NUMBER_FIELDS = None
ITEMS_PER_PAGE = 24

# Shopify App
SHOPIFY_API_KEY = os.environ['SHOPIFY_API_KEY']
SHOPIFY_API_SECRET = os.environ['SHOPIFY_API_SECRET']
SHOPIFY_API_SCOPE = ','.join([
    'write_content', 'write_products', 'write_customers',
    'write_orders', 'write_fulfillments', 'write_shipping', 'read_analytics',
    'write_inventory', 'read_locations', 'read_all_orders'
])

# Intercom API
INTERCOM_APP_ID = os.environ.get('INTERCOM_APP_ID')
INTERCOM_SECRET_KEY = os.environ.get('INTERCOM_SECRET_KEY')
INTERCOM_ACCESS_TOKEN = os.environ.get('INTERCOM_ACCESS_TOKEN')

# AWS S3
AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']

S3_STATIC_BUCKET = os.environ.get('S3_BUCKET_NAME', 'shopifiedapp-assets')
S3_PRODUCT_FEED_BUCKET = os.environ.get('S3_PRODUCT_FEED_BUCKET', 'shopifiedapp-feeds')
S3_UPLOADS_BUCKET = os.environ.get('S3_UPLOADS_BUCKET', 'shopifiedapp-uploads')
S3_SECRET_BUCKET = os.environ.get('S3_SECRET_BUCKET', S3_STATIC_BUCKET)

AWS_STORAGE_BUCKET_NAME = S3_STATIC_BUCKET  # Default bucket

USE_WHITENOISE = os.environ.get('USE_WHITENOISE')

# Django Storage
if not DEBUG:
    AWS_S3_SECURE_URLS = False
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_URL_PROTOCOL = ''
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('S3_CUSTOM_DOMAIN', 'd2kadg5e284yn4.cloudfront.net')

    AWS_IS_GZIPPED = False
    AWS_HEADERS = {
        'Cache-Control': 'max-age=604800',
    }
    GZIP_CONTENT_TYPES = (
        'text/css',
        'application/javascript',
        'application/x-javascript',
        'text/javascript'
    )

    STATICFILES_LOCATION = 'static'
    MEDIAFILES_LOCATION = 'media'

    if not USE_WHITENOISE:
        STATICFILES_STORAGE = 'app.storage.CachedS3BotoStorage'
        DEFAULT_FILE_STORAGE = 'app.storage.CachedMediaS3BotoStorage'
        STATIC_URL = "//%s/%s/" % (AWS_S3_CUSTOM_DOMAIN, STATICFILES_LOCATION)

        COMPRESS_STORAGE = 'app.storage.CachedS3BotoStorage'

# Django Compressor
COMPRESS_ENABLED = not DEBUG
COMPRESS_OFFLINE = True
COMPRESS_OUTPUT_DIR = 'cdn'
COMPRESS_ROOT = STATIC_ROOT
COMPRESS_URL = STATIC_URL

COMPRESS_JS_FILTERS = [
    'compressor.filters.yuglify.YUglifyJSFilter'
]

COMPRESS_CSS_FILTERS = [
    # Creates absolute urls from relative ones.
    'compressor.filters.css_default.CssAbsoluteFilter',
    # CSS minimizer.
    'compressor.filters.yuglify.YUglifyJSFilter'
]

# JVZoo
JVZOO_SECRET_KEY = os.environ['JVZOO_SECRET']

# Zaxaa
ZAXAA_API_SIGNATURE = os.environ.get('ZAXAA_API_SIGNATURE')

# Celery Config

BROKER_URL = REDISCLOUD_URL
CELERY_RESULT_BACKEND = REDISCLOUD_URL
CELERY_ACCEPT_CONTENT = ['json', 'msgpack', 'yaml']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_REDIS_MAX_CONNECTIONS = 10
CELERY_TASK_RESULT_EXPIRES = 1800
CELERYD_TASK_SOFT_TIME_LIMIT = 900
BROKER_TRANSPORT_OPTIONS = {'max_connections': 10}
BROKER_POOL_LIMIT = 10
CELERYD_CONCURRENCY = 4
CELERYD_MAX_TASKS_PER_CHILD = 3000
CELERY_ROUTES = {
    "leadgalaxy.tasks.export_product": {"queue": "priority_high"},
    "leadgalaxy.tasks.order_save_changes": {"queue": "priority_high"},
    "leadgalaxy.tasks.add_ordered_note": {"queue": "priority_high"},
    "leadgalaxy.tasks.calculate_user_statistics": {"queue": "priority_high"},
    "commercehq_core.tasks.product_export": {"queue": "priority_high"},
    "commercehq_core.tasks.product_update": {"queue": "priority_high"},
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'shopified_core.authentication.TokenAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'shopified_core.paginators.RESTResultsPagination',
    'PAGE_SIZE': 20,
}

if not DEBUG:
    REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = (
        'rest_framework.renderers.JSONRenderer',
    )

PRICE_MONITOR_EVENTS = {
    'product:offline': None,
    'variant:quantity': None,
    'variant:price': None,
    'variant:var_added': None,
    'variant:var_removed': None,
}

HOOK_EVENTS = PRICE_MONITOR_EVENTS.copy()
HOOK_EVENTS.update({
    'shopify_order_created': None,
    'shopify_order_cancelled': None,
    'shopify_order_status_changed': None,
    'alert_created': None,
    'order_track_source_status_changed': None,
    'order_track_source_tracking_changed': None,
})

HOOK_DELIVERER = 'zapier_core.tasks.deliver_hook_wrapper'

SENTRY_DSN = os.environ.get('SENTRY_DSN')
SENTRY_CLIENT = 'app.sentry.SentryClient'
SENTRY_PROCESSORS = (
    'raven.processors.SanitizePasswordsProcessor',
    'app.sentry.SentryDataProcessor',
)

# default Aliexpress Affiliate
DEFAULT_ALIEXPRESS_AFFILIATE = 'ali'

# Auto Aliexpress fulfillment server API
FULFILLBOX_API_URL = os.environ.get('FULFILLBOX_API_URL')
if FULFILLBOX_API_URL:
    FULFILLBOX_API_URL = FULFILLBOX_API_URL.rstrip('/')

# Stripe
STRIPE_PUBLIC_KEY = os.environ['STRIPE_PUBLIC_KEY']
STRIPE_SECRET_KEY = os.environ['STRIPE_SECRET_KEY']
STRIP_TRIAL_DISCOUNT_DAYS = 10
STRIP_TRIAL_DISCOUNT_COUPON = 'TRIAL-1MONTH'

# Pusher
PUSHER_APP_ID = os.environ.get('PUSHER_APP_ID')
PUSHER_KEY = os.environ.get('PUSHER_KEY')
PUSHER_SECRET = os.environ.get('PUSHER_SECRET')

# OneSignal
ONESIGNAL_APP_ID = os.environ.get('ONESIGNAL_APP_ID')
ONESIGNAL_API_KEY = os.environ.get('ONESIGNAL_API_KEY')

# StatusPage
STATUSPAGE_API_KEY = os.environ.get('STATUSPAGE_API_KEY')

# Clipping Magic
CLIPPINGMAGIC_API_ID = os.environ.get('CLIPPINGMAGIC_API_ID')
CLIPPINGMAGIC_API_SECRET = os.environ.get('CLIPPINGMAGIC_API_SECRET')

FACEBOOK_PIXEL_ID = os.environ.get('FACEBOOK_PIXEL_ID')

KEEN_PROJECT_ID = os.environ.get('KEEN_PROJECT_ID')

# GearBubble
GEARBUBBLE_STAGING_URL = 'http://staging-gearbubble.com'
GEARBUBBLE_LIVE_URL = 'https://www.gearbubble.com'
GEARBUBBLE_DEFAULT_QTY = 100

# price-monitor
PRICE_MONITOR_HOSTNAME = os.environ.get('PRICE_MONITOR_HOSTNAME')
PRICE_MONITOR_USERNAME = os.environ.get('PRICE_MONITOR_USERNAME')
PRICE_MONITOR_PASSWORD = os.environ.get('PRICE_MONITOR_PASSWORD')

# Profits Dashboard FB Ads
FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID')
FACEBOOK_APP_SECRET = os.environ.get('FACEBOOK_APP_SECRET')

ELASTICSEARCH_API = os.environ.get('FOUNDELASTICSEARCH_URL', '').split(',')
ELASTICSEARCH_AUTH = (os.environ.get('FOUNDELASTICSEARCH_USER'), os.environ.get('FOUNDELASTICSEARCH_PASSWORD'))

TAPFILIATE_API_KEY = os.environ.get('TAPFILIATE_API_KEY')

# Youtube Ads App
YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')

# CallFlex
PHONE_AUTOMATION_MONTH_LIMIT_TOLLFREE = os.environ.get('PHONE_AUTOMATION_MONTH_LIMIT_TOLLFREE', '12000')  # in seconds.  1 hr per month for user
PHONE_AUTOMATION_MONTH_LIMIT_LOCAL = os.environ.get('PHONE_AUTOMATION_MONTH_LIMIT_LOCAL', '12000')  # in seconds.  1 hr per month for user
TWILIO_SID = os.environ.get('TWILIO_SID')
TWILIO_TOKEN = os.environ.get('TWILIO_TOKEN')
if DEBUG:
    AWS_AUDIO_TRANSCODE_PIPELINE_ID = os.environ.get('AWS_AUDIO_TRANSCODE_PIPELINE_ID', '1545231733178-6djxwp')
else:
    AWS_AUDIO_TRANSCODE_PIPELINE_ID = os.environ.get('AWS_AUDIO_TRANSCODE_PIPELINE_ID', '1545230355460-asr0hb')
EXTRA_TOLLFREE_NUMBER_PRICE = 5  # USD
EXTRA_LOCAL_NUMBER_PRICE = 3  # USD
EXTRA_TOLLFREE_MINUTE_PRICE = 0.05  # USD per minute
EXTRA_LOCAL_MINUTE_PRICE = 0.02  # USD per minute
CALLFLEX_OVERAGES_MAX_NUMBERS = 10  # user can never go over this limit  of phone number when adding as overages
CALLFLEX_OVERAGES_MAX_MINUTES = 1000  # user can never go over this limit of minutes when adding as overages

CALLFLEX_SHOPIFY_USAGE_MAX_PENDING = 50  # after reaching this pending limit (in USD) it deletes all user's twilio phones

# Baremetrics (Customer Tags)
BAREMETRICS_API_KEY = os.environ.get('BAREMETRICS_API_KEY')
BAREMETRICS_TAGS_FIELD = os.environ.get('BAREMETRICS_TAGS_FIELD', 753)

# Baremetrics
BAREMETRICS_ACCESS_TOKEN = os.environ.get('BAREMETRICS_ACCESS_TOKEN')
BAREMETRICS_JWT_TOKEN_KEY = os.environ.get('BAREMETRICS_JWT_TOKEN_KEY')
PHONE_AUTOMATION_WARNING_LIMIT = 0.75  # percent. when reached - send warning email
