from django.contrib.auth.models import User

from logistics.models import Order
from shopified_core.commands import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Process 3PL refund status'

    def add_arguments(self, parser):
        parser.add_argument('-u', '--user', default=None, help='Process only specified user')
        parser.add_argument('-p', '--progress', action='store_true', help='Show Reset Progress')

    def start_command(self, *args, user=None, progress=False, **options):
        orders = Order.objects.filter(refund_at__isnull=False, refunded_at__isnull=True)

        if user:
            user = User.objects.get(id=user).models_user
            orders = orders.filter(warehouse__user=user)

        if progress:
            self.progress_total(orders.count())

        self.write(f'Refreshing {self.style.SUCCESS(orders.count())} refund statuses')
        for order in orders:
            order.refresh_refund_status()
            if progress:
                self.progress_update()

        if not progress:
            self.write_success('Finished')
