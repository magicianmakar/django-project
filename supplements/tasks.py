import json

from app.celery_base import CaptureFailure, celery_app
from lib.exceptions import capture_exception
from shopified_core.utils import hash_text

from .lib.shipstation import create_shipstation_order, get_address, prepare_shipstation_data
from .models import PLSOrder
from .utils.payment import Util


@celery_app.task(base=CaptureFailure)
def update_shipstation_address(order_id, order_number, order_line_items, store_id, store_type):
    try:
        pls_order = PLSOrder.objects.get(order_number=order_number)
        if not pls_order.is_fulfilled:
            store = Util().get_store(store_id, store_type)
            order = store.get_order(order_id)

            ship_addr = get_address(order['shipping_address'])
            hash = hash_text(json.dumps(ship_addr, sort_keys=True))
            if pls_order.shipping_address_hash != str(hash):
                for line_item in order_line_items:
                    product = store.get_product(line_item['product_id'], store)
                    line_item['sku'] = product.user_supplement.shipstation_sku
                    line_item['user_supplement'] = product.user_supplement
                    line_item['label'] = product.user_supplement.current_label

                shipstation_data = prepare_shipstation_data(pls_order,
                                                            order,
                                                            order_line_items,
                                                            )
                shipstation_data.update({
                    'orderKey': pls_order.shipstation_key,
                })
                create_shipstation_order(pls_order, shipstation_data)
    except PLSOrder.DoesNotExist:
        pass
    except Exception:
        capture_exception(level='warning')
