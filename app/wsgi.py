import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.db.backends.signals import connection_created

from raven.contrib.django.raven_compat.middleware.wsgi import Sentry
from whitenoise.django import DjangoWhiteNoise

if settings.DEBUG:
    from django import VERSION
    TARGET = (2, 2)
    assert VERSION[:2] == TARGET, ('\nYou are using a different Django version, '
                                   f'\nYour version is {VERSION[0]}.{VERSION[1]} it should be {TARGET[0]}.{TARGET[1]}')

application = Sentry(get_wsgi_application())

if settings.USE_WHITENOISE:
    application = DjangoWhiteNoise(application)


def setup_postgres_timeout(connection, **kwargs):
    if not settings.DATABASE_STATEMENT_TIMEOUT or connection.vendor != 'postgresql':
        return

    # Timeout statements after settings.DATABASE_STATEMENT_TIMEOUT (ms).
    with connection.cursor() as cursor:
        cursor.execute('SET statement_timeout TO {};'.format(settings.DATABASE_STATEMENT_TIMEOUT))


if settings.DATABASE_STATEMENT_TIMEOUT:
    connection_created.connect(setup_postgres_timeout)
