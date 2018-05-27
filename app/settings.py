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

# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'i+acxn5(akgsn!sr4^qgf(^m&*@+g1@u^t@=8s@axc41ml*f=s'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = (os.environ.get('DEBUG_APP') == 'TRUE')

ALLOWED_HOSTS = [
    '.shopifiedapp.com',
    '.dropified.com',
]

APP_DOMAIN = os.environ.get('APP_DOMAIN', 'app.dropified.com')
APP_URL = os.environ.get('APP_URL', 'https://{}'.format(APP_DOMAIN))

# Application definition

INSTALLED_APPS = (
    'flat',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'raven.contrib.django.raven_compat',
    'widget_tweaks',    # For forms
    'hijack',
    'compat',
    'compressor',
    'storages',
    'django_extensions',
    'test_without_migrations',
    'last_seen',
    'polymorphic',

    'article',
    'leadgalaxy',
    'shopify_oauth',
    'shopify_orders',
    'shopify_revision',
    'stripe_subscription',
    'shopify_subscription',
    'plan_checkout',
    'product_feed',
    'data_store',
    'product_alerts',
    'analytic_events',
    'order_exports',
    'order_imports',
    'profit_dashboard',
    'affiliations',
    'subusers',

    'commercehq_core',
    'dropwow_core',
    'woocommerce_core',
)

MIDDLEWARE_CLASSES = (
    # 'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'hijack.middleware.HijackRemoteUserMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
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
                'article.context_processors.sidebarlinks',
                'leadgalaxy.context_processors.extra_bundles',
                'leadgalaxy.context_processors.extension_release',
                'leadgalaxy.context_processors.intercom',
                'leadgalaxy.context_processors.facebook_pixel',
                'leadgalaxy.context_processors.store_limits_check',
                'subusers.context_processors.template_config',
                'analytic_events.context_processors.analytic_events',
            ],
        },
    },
]

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    # other finders..
    'compressor.finders.CompressorFinder',
)

WSGI_APPLICATION = 'app.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    },
    'store_db': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'store_db.sqlite3'),
    }
}

# Cache
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "{0}/{1}".format(os.environ['REDISCLOUD_CACHE'], 0),
    },
    "orders": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "{0}/{1}".format(os.environ['REDISCLOUD_ORDERS'], 0),
    }
}

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Parse database configuration from $DATABASE_URL
if os.environ.get('DATABASE_URL'):
    DATABASES['default'] = dj_database_url.config()
    DATABASES['default']['ENGINE'] = 'django_postgrespool'

if os.environ.get('DATA_STORE_DATABASE_URL'):
    DATABASES['store_db'] = dj_database_url.parse(os.environ['DATA_STORE_DATABASE_URL'])
    DATABASES['store_db']['ENGINE'] = 'django_postgrespool'

DATABASE_ROUTERS = [
    'data_store.routers.DataStoreRouter',
]

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ('HTTP_X_PROXY_PROTOCOL', 'https')

SECURE_SSL_REDIRECT = not DEBUG and not os.environ.get('DISABLE_SSL_REDIRECT')
SECURE_REDIRECT_EXEMPT = [
    '^webhook/',
    '^marketing/feeds/',
]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.8/howto/static-files/

BASE_DIR2 = os.path.dirname(os.path.abspath(__file__))
STATIC_ROOT = 'staticfiles'
STATIC_URL = '/static/'

STATICFILES_DIRS = (
    os.path.join(BASE_DIR2, 'static'),
)

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = 'http://localhost/'

# Simplified static file serving.
# https://warehouse.python.org/project/whitenoise/
STATICFILES_STORAGE = 'whitenoise.django.GzipManifestStaticFilesStorage'

HIJACK_LOGIN_REDIRECT_URL = '/'
HIJACK_LOGOUT_REDIRECT_URL = '/'
HIJACK_DISPLAY_ADMIN_BUTTON = False
HIJACK_USE_BOOTSTRAP = True

EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_HOST_USER = os.environ.get('SENDGRID_USERNAME')
EMAIL_HOST_PASSWORD = os.environ.get('SENDGRID_PASSWORD')
EMAIL_PORT = 587
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = "support@dropified.com"

# Shopify App
SHOPIFY_API_KEY = os.environ['SHOPIFY_API_KEY']
SHOPIFY_API_SECRET = os.environ['SHOPIFY_API_SECRET']
SHOPIFY_API_SCOPE = u','.join([
    'write_apps', 'write_content', 'write_products', 'write_customers',
    'write_orders', 'write_fulfillments', 'write_shipping', 'read_analytics',
    'write_inventory', 'read_locations'
])

# Slack API
SLACK_USERS_TEAM_API = os.environ.get('SLACK_USERS_TEAM_API')
SLACK_ECOM_TEAM_API = os.environ.get('SLACK_ECOM_TEAM_API')

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

AWS_STORAGE_BUCKET_NAME = S3_STATIC_BUCKET  # Default bucket

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
    # 'compressor.filters.jsmin.SlimItFilter'
]

COMPRESS_CSS_FILTERS = [
    # Creates absolute urls from relative ones.
    'compressor.filters.css_default.CssAbsoluteFilter',
    # CSS minimizer.
    # 'compressor.filters.cssmin.CSSMinFilter',
    'compressor.filters.yuglify.YUglifyJSFilter'
]

# JVZoo
JVZOO_SECRET_KEY = os.environ['JVZOO_SECRET']

# Zaxaa
ZAXAA_API_SIGNATURE = os.environ.get('ZAXAA_API_SIGNATURE')

# Celery Config

BROKER_URL = os.environ['REDISCLOUD_URL']
CELERY_RESULT_BACKEND = os.environ['REDISCLOUD_URL']
CELERY_ACCEPT_CONTENT = ['pickle', 'json', 'msgpack', 'yaml']
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
    "dropwow_core.tasks.fulfill_dropwow_items": {"queue": "priority_high"},
}

SENTRY_DSN = os.environ.get('SENTRY_DSN')
if not DEBUG and SENTRY_DSN:
    RAVEN_CONFIG = {
        'dsn': SENTRY_DSN
    }

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

WICKED_REPORTS_API = os.environ.get('WICKED_REPORTS_API')

# Dropwow
DROPWOW_API_HOSTNAME = os.environ.get('DROPWOW_API_HOSTNAME')
DROPWOW_API_USERNAME = os.environ.get('DROPWOW_API_USERNAME')
DROPWOW_API_PASSWORD = os.environ.get('DROPWOW_API_PASSWORD')

# price-monitor
PRICE_MONITOR_HOSTNAME = os.environ.get('PRICE_MONITOR_HOSTNAME')
PRICE_MONITOR_USERNAME = os.environ.get('PRICE_MONITOR_USERNAME')
PRICE_MONITOR_PASSWORD = os.environ.get('PRICE_MONITOR_PASSWORD')

# Profits Dashboard FB Ads
FACEBOOK_APP_ID = os.environ.get('FACEBOOK_APP_ID')
FACEBOOK_APP_SECRET = os.environ.get('FACEBOOK_APP_SECRET')

ELASTICSEARCH_API = os.environ.get('FOUNDELASTICSEARCH_URL', '').split(',')
ELASTICSEARCH_AUTH = (os.environ.get('FOUNDELASTICSEARCH_USER'), os.environ.get('FOUNDELASTICSEARCH_PASSWORD'))

LEAD_DYNO_API_KEY = os.environ.get('LEAD_DYNO_API_KEY')
