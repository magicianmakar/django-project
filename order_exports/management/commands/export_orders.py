import arrow

from django.core.management.base import BaseCommand

from order_exports.api import ShopifyOrderExportAPI
from order_exports.models import OrderExport

from raven.contrib.django.raven_compat.models import client as raven_client


class Command(BaseCommand):

    def handle(self, *args, **options):
        try:
            self.start_command(*args, **options)
        except:
            raven_client.captureException()

    def start_command(self, *args, **options):
        start, end = self.get_scheduled_time()
        for order_export in OrderExport.objects.filter(schedule__gte=start, schedule__lte=end):
            api = ShopifyOrderExportAPI(order_export)
            api.generate_query()

    def get_scheduled_time(self):
        """ Returns start and end time of the current hour.
            Ex: [12:00, 12:59]
        """

        return [i.time() for i in arrow.now().span('hour')]
