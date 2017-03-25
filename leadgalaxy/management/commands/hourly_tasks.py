import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from raven.contrib.django.raven_compat.models import client as raven_client

from product_feed.models import FeedStatus
from product_feed.feed import generate_product_feed


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        self.generate_product_feeds()

    def generate_product_feeds(self):
        an_hour_ago = timezone.now() - datetime.timedelta(hours=1)
        statuses = FeedStatus.objects.filter(fb_access_at__gte=an_hour_ago)
        for status in statuses:
            generate_product_feed(status, nocache=True)
