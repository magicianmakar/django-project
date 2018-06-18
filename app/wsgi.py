"""
WSGI config for app project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/howto/deployment/wsgi/
"""

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.db.backends.signals import connection_created

from raven.contrib.django.raven_compat.middleware.wsgi import Sentry

application = Sentry(get_wsgi_application())


def setup_postgres_timeout(connection, **kwargs):
    if not settings.DATABASE_STATEMENT_TIMEOUT or connection.vendor != 'postgresql':
        return

    # Timeout statements after settings.DATABASE_STATEMENT_TIMEOUT (ms).
    with connection.cursor() as cursor:
        cursor.execute('SET statement_timeout TO {};'.format(settings.DATABASE_STATEMENT_TIMEOUT))


if settings.DATABASE_STATEMENT_TIMEOUT:
    connection_created.connect(setup_postgres_timeout)
