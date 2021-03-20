from lib.exceptions import capture_exception

from app.celery_base import celery_app, CaptureFailure
from shopified_core.utils import hash_url_filename
from shopified_core.models_utils import get_store_model

from . import utils


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def generate_mockup(self, store_type, store_id, sku, variant_id, uploaded_images=None, paired=True):
    if uploaded_images is None:
        uploaded_images = []

    store = None
    try:
        store_model = get_store_model(store_type)
        store = store_model.objects.get(pk=store_id)

        layer_app = utils.LayerApp()
        mockup = layer_app.generate_mockup(variant_id, *uploaded_images, paired=paired)
        assert isinstance(mockup, str), 'Wrong mockup data'

        store.pusher_trigger('prints-mockup', {
            'sku': sku,
            'success': True,
            'mockup': mockup,
            'mockup_hash': hash_url_filename(mockup),
            'variant_id': variant_id,
            'artworks': uploaded_images,
        })

    except:
        capture_exception()

        if store:
            store.pusher_trigger('prints-mockup', {
                'sku': sku,
                'success': False,
                'error': 'Mockup not generated',
            })
