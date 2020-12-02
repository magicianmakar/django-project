from app.celery_base import celery_app, CaptureFailure

from lib.exceptions import capture_exception

from shopified_core.utils import get_store_model
from .lib.shipstation import create_shipstation_order, prepare_shipstation_data
from .models import UserSupplement, UserSupplementLabel, PLSOrder


@celery_app.task(base=CaptureFailure)
def update_shipstation_address(pls_order_id, order_line_items, store_id, store_type):
    try:
        pls_order = PLSOrder.objects.get(id=pls_order_id)
        store = get_store_model(store_type).objects.get(id=store_id)
        order = store.get_order(pls_order.store_order_id)

        for line_item in order_line_items:
            line_item['user_supplement'] = UserSupplement.objects.get(id=line_item['user_supplement_id'])
            line_item['label'] = UserSupplementLabel.objects.get(id=line_item['label_id'])

        pay_taxes = (pls_order.taxes or pls_order.duties) > 0
        data = prepare_shipstation_data(
            pls_order,
            order,
            order_line_items,
            pay_taxes)
        data.update({
            'orderKey': pls_order.shipstation_key,
        })
        create_shipstation_order(pls_order, data)

    except Exception:
        capture_exception(level='warning')
