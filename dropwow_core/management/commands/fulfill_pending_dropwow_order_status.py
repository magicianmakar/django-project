from django.db.models import Q

from shopified_core.management import DropifiedBaseCommand

from dropwow_core.models import DropwowOrderStatus
from dropwow_core.utils import fulfill_dropwow_order


class Command(DropifiedBaseCommand):
    help = 'Fulfill Pending Dropwow Items'

    def start_command(self, *args, **options):
        dropwow_order_statuses = DropwowOrderStatus.objects\
            .filter(Q(order_id='') | Q(order_id__isnull=True))\
            .filter(pending=True)
        fulfilled_orders = 0
        for dropwow_order_status in dropwow_order_statuses:
            if (fulfill_dropwow_order(dropwow_order_status)):
                fulfilled_orders += 1
        self.write_success('Fulfilled {} Dropwow Orders'.format(fulfilled_orders))
