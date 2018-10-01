from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure

from leadgalaxy.models import ShopifyStore

from profit_dashboard.models import FacebookAccess


@celery_app.task(bind=True, base=CaptureFailure)
def fetch_facebook_insights(self, store_id, facebook_access_ids):
    from .utils import get_facebook_ads

    store = ShopifyStore.objects.get(pk=store_id)
    try:
        for access in FacebookAccess.objects.filter(id__in=facebook_access_ids):
            get_facebook_ads(access.id, store)

        store.pusher_trigger('facebook-insights', {
            'success': True
        })
    except Exception:
        raven_client.captureException()

        store.pusher_trigger('facebook-insights', {
            'success': False,
            'error': 'Facebook API Error',
        })
