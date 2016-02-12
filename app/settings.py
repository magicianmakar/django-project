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


# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'i+acxn5(akgsn!sr4^qgf(^m&*@+g1@u^t@=8s@axc41ml*f=s'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = (os.environ.get('DEBUG_APP') == 'TRUE')

ALLOWED_HOSTS = [
    'app.shopifiedapp.com',
]

# Application definition

INSTALLED_APPS = (
    'flat',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'widget_tweaks',    # For forms
    'hijack',
    'multiselectfield',
    'compressor',
    'storages',

    'article',
    'leadgalaxy'
)

MIDDLEWARE_CLASSES = (
    'django.middleware.gzip.GZipMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'hijack.middleware.HijackRemoteUserMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
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
    }
}

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

SESSION_COOKIE_AGE = 6048000

# Parse database configuration from $DATABASE_URL
if os.environ.get('DATABASE_URL'):
    DATABASES['default'] = dj_database_url.config()
    DATABASES['default']['ENGINE'] = 'django_postgrespool'

# Honor the 'X-Forwarded-Proto' header for request.is_secure()
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Allow all host headers
ALLOWED_HOSTS = ['*']

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

HIJACK_LOGIN_REDIRECT_URL = "/"  # where you want to be redirected to, after hijacking the user.
REVERSE_HIJACK_LOGIN_REDIRECT_URL = "/"  # where you want to be redirected to, after releasing the user.

EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_HOST_USER = os.environ.get('SENDGRID_USERNAME')
EMAIL_HOST_PASSWORD = os.environ.get('SENDGRID_PASSWORD')
EMAIL_PORT = 587
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = "noreply@shopifiedapp.com"

# Django Storage
if not DEBUG:
    AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
    AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
    AWS_STORAGE_BUCKET_NAME = os.environ['S3_BUCKET_NAME']

    AWS_S3_SECURE_URLS = False
    AWS_QUERYSTRING_AUTH = False

    STATICFILES_LOCATION = 'static'
    MEDIAFILES_LOCATION = 'media'

    STATICFILES_STORAGE = 'app.storage.CachedS3BotoStorage'
    DEFAULT_FILE_STORAGE = 'app.storage.CachedMediaS3BotoStorage'
    STATIC_URL = "http://%s.s3.amazonaws.com/%s/" % (AWS_STORAGE_BUCKET_NAME, STATICFILES_LOCATION)

    COMPRESS_STORAGE = 'app.storage.CachedS3BotoStorage'

# Django Compressor
COMPRESS_ENABLED = not DEBUG
COMPRESS_OFFLINE = True
COMPRESS_OUTPUT_DIR = ''
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

COMPRESS_YUGLIFY_BINARY = '/app/node_modules/.bin/uglifyjs'
