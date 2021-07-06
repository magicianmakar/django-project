import arrow

from shopified_core.commands import DropifiedBaseCommand
from order_exports.utils import ShopifyOrderExport
from order_exports.models import OrderExport


class Command(DropifiedBaseCommand):

    def start_command(self, *args, **options):
        start, end = [i.time() for i in arrow.now().span('hour')]

        for order_export in OrderExport.objects.filter(schedule__gte=start, schedule__lte=end):
            api = ShopifyOrderExport(order_export)
            api.generate_query()
