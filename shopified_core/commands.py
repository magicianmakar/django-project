import sys

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

import requests
from tqdm import tqdm

from lib.exceptions import capture_exception


class DropifiedBaseCommand(BaseCommand):
    progress_bar = None

    def handle(self, *args, **options):
        try:
            requests.head(settings.APP_URL, params={
                'command': sys.argv[-1]
            }).raise_for_status()

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError):
            management_command = sys.argv[1] if len(sys.argv) > 1 else ''
            if not settings.DEBUG and management_command != 'test':
                self.stderr.write('Web app is not available %s' % sys.argv[-1])
                capture_exception(level='warning')

                return

        assert hasattr(self, 'start_command')

        self._statement_timeout()

        try:
            self.start_command(*args, **options)

        except KeyboardInterrupt:
            self.stdout.write('Exit...')

        except:
            capture_exception()

        if self.progress_bar:
            self.progress_bar.close()

    def write(self, msg, style_func=None, ending=None, show=True):
        if not show:
            return

        if self.progress_bar:
            self.progress_bar.write(msg)
        else:
            self.stdout.write(msg, style_func, ending)

    def write_success(self, msg, show=True):
        if not show:
            return

        if self.progress_bar:
            self.progress_bar.write(msg)
        else:
            self.stdout.write(self.style.SUCCESS(msg))

    def raven_context_from_store(self, client, store, tags=None):
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

    def progress_total(self, total, enable=True):
        if enable:
            self.progress_bar = tqdm(total=total, smoothing=0)

    def progress_update(self, p=1, desc=None):
        if self.progress_bar:
            self.progress_bar.update(p)

            if desc:
                self.progress_bar.set_description(desc)

    def progress_description(self, desc=None):
        if self.progress_bar:
            self.progress_bar.set_description(desc)

    def progress_write(self, msg):
        if self.progress_bar:
            self.progress_bar.write(msg)

    def progress_close(self):
        if self.progress_bar:
            self.progress_bar.close()
            self.progress_bar = None
