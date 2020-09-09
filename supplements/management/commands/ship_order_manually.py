from django.core.management.base import CommandError

from shopified_core.management import DropifiedBaseCommand
from shopified_core.shipping_helper import country_from_code

from supplements.lib.shipstation import create_shipstation_order, prepare_shipstation_data
from supplements.models import PLSOrder
from supplements.utils.payment import Util


class Command(DropifiedBaseCommand):
    help = 'Ship Orders Manually to ShipStation'

    def add_arguments(self, parser):
        parser.add_argument(
            'order_id',
            default=False,
            help='Ship specified order'
        )

    def start_command(self, *args, **options):
        order_number, order_id = options['order_id'].split('-')

        try:
            pls_order = PLSOrder.objects.get(id=order_id, order_number=order_number)
        except PLSOrder.DoesNotExist:
            raise CommandError(f'Order {order_id} does not exist')
        if pls_order.shipstation_key:
            raise CommandError(f'Order {order_id} was already sent to ShipStation')

        util = Util()
        store = util.get_store(pls_order.store_id, pls_order.store_type)
        order = store.get_order(pls_order.store_order_id)

        address = order['shipping_address']
        address['country'] = country_from_code(address['country_code'], address['country'])

        for line_item in order['line_items']:
            pls_order_line = pls_order.order_items.get(line_id=line_item['id'])
            user_supplement = pls_order_line.label.user_supplement
            line_item['user_supplement'] = user_supplement
            line_item['sku'] = user_supplement.shipstation_sku
            line_item['label'] = user_supplement.current_label

        shipstation_data = prepare_shipstation_data(pls_order,
                                                    order,
                                                    order['line_items'])
        create_shipstation_order(pls_order, shipstation_data)
