from django.core.management.base import BaseCommand

from raven.contrib.django.raven_compat.models import client as raven_client


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        pass
