from app.celery_base import celery_app, CaptureFailure
from lib.exceptions import capture_exception
from product_core.utils import update_product_es, delete_product_es
from shopified_core.models_utils import get_product_model


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def index_product_task(self, product_id, platform):
    try:
        product = get_product_model(platform).objects.get(id=product_id)
        update_product_es(product, platform)
    except:
        capture_exception(level='warning')


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def delete_product_task(self, product_id, platform):
    try:
        delete_product_es(product_id, platform)
    except:
        capture_exception(level='warning')
