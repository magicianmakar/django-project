import traceback
import requests

from django.conf import settings
from django.core.management.base import BaseCommand

from raven.contrib.django.raven_compat.models import client as raven_client
import sys


class DropifiedBaseCommand(BaseCommand):
    def handle(self, *args, **options):
        try:
            requests.head(settings.APP_URL, params={
                'command': sys.argv[-1]
            }).raise_for_status()

        except requests.exceptions.HTTPError:
            if not settings.DEBUG:
                self.stderr.write('Web app is not available %s' % sys.argv[-1])
                raven_client.captureException(level='warning')

                return

        assert hasattr(self, 'start_command')

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
        self.stdout.write(self.style.MIGRATE_SUCCESS(message))
