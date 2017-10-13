import arrow

from shopified_core.management import DropifiedBaseCommand
from order_exports.api import ShopifyOrderExportAPI
from order_exports.models import OrderExport


class Command(DropifiedBaseCommand):

    def start_command(self, *args, **options):
        start, end = [i.time() for i in arrow.now().span('hour')]

        for order_export in OrderExport.objects.filter(schedule__gte=start, schedule__lte=end):
            api = ShopifyOrderExportAPI(order_export)
            api.generate_query()
