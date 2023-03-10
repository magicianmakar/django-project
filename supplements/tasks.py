from celery.exceptions import SoftTimeLimitExceeded

from app.celery_base import celery_app, CaptureFailure
from lib.exceptions import capture_exception
from shopified_core.models_utils import get_store_model
from shopified_core.utils import hash_text
from .lib.shipstation import LimitExceededError, prepare_shipping_data, create_shipstation_order, get_orders_lock
from .models import PLSOrder, PLSOrderLine


@celery_app.task(base=CaptureFailure)
def update_shipstation_address(pls_order_id, store_id, store_type):
    try:
        pls_order = PLSOrder.objects.get(id=pls_order_id)
        store = get_store_model(store_type).objects.get(id=store_id)
        order = store.get_order(pls_order.store_order_id)

        ship_to, bill_to = prepare_shipping_data(order)
        pls_order.shipping_address_hash = hash_text(ship_to)
        pls_order.shipping_address = ship_to
        pls_order.billing_address = bill_to

        shipstation_acc = PLSOrderLine.objects.filter(pls_order=pls_order_id).first().label.user_supplement.pl_supplement.shipstation_account
        create_shipstation_order(pls_order, shipstation_acc)

        # Persisting changes will prevent triggering a later address change
        pls_order.save()

    except Exception:
        capture_exception(level='warning')


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def create_shipstation_orders(self, token):
    """Send all paid orders to shipstation while respecting any http 429 responses"""

    # # Prevent running twice
    lock = get_orders_lock(token)
    if not lock:
        return False

    try:
        order = PLSOrder.objects.filter(
            shipstation_key='',
            status__in=[PLSOrder.PAID, PLSOrder.SHIPPING_ERROR],
        ).first()

        orderlines = PLSOrderLine.objects.filter(pls_order=order.id)

        while order:
            for orderline in orderlines:
                try:
                    shipstation_acc = orderline.label.user_supplement.pl_supplement.shipstation_account
                    create_shipstation_order(order, shipstation_acc)

                except LimitExceededError as e:
                    lock.release()
                    raise self.retry(exc=e, countdown=e.retry_after)

                except:
                    capture_exception()
                    order.shipstation_retries += 1
                    order.status = PLSOrder.SHIPPING_ERROR
                    order.save()

            order = PLSOrder.objects.filter(
                shipstation_key='',
                status__in=[PLSOrder.PAID, PLSOrder.SHIPPING_ERROR],
            ).first()

    except SoftTimeLimitExceeded:
        pass

    lock.release()
