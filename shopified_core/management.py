import traceback
import requests

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from raven.contrib.django.raven_compat.models import client as raven_client
import sys


class DropifiedBaseCommand(BaseCommand):
    def handle(self, *args, **options):
        try:
            requests.head(settings.APP_URL, params={
                'command': sys.argv[-1]
            }).raise_for_status()

        except requests.exceptions.HTTPError:
            management_command = sys.argv[1] if len(sys.argv) > 1 else ''
            if not settings.DEBUG and management_command != 'test':
                self.stderr.write('Web app is not available %s' % sys.argv[-1])
                raven_client.captureException(level='warning')

                return

        assert hasattr(self, 'start_command')

        self._statement_timeout()

        try:
            self.start_command(*args, **options)

        except KeyboardInterrupt:
            self.stdout.write('Exit...')

        except:
            if settings.DEBUG:
                traceback.print_exc()

            raven_client.captureException()

    def write(self, msg, style_func=None, ending=None):
        self.stdout.write(msg, style_func, ending)

    def write_success(self, message):
        self.stdout.write(self.style.SUCCESS(message))

    def raven_context_from_store(self, client, store, tags={}):
        client.user_context({
            'id': store.user.id,
            'username': store.user.username,
            'email': store.user.email
        })

        if hasattr(store, 'shop'):
            tags['store'] = store.shop

        if tags:
            client.tags_context(tags)

    def _statement_timeout(self):
        if settings.COMMAND_STATEMENT_TIMEOUT and connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SET statement_timeout TO {};'.format(settings.COMMAND_STATEMENT_TIMEOUT))
