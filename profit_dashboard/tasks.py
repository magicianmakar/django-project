from django.contrib.auth.models import User

from raven.contrib.django.raven_compat.models import client as raven_client

from app.celery import celery_app, CaptureFailure


@celery_app.task(bind=True, base=CaptureFailure)
def fetch_facebook_insights(self, user_id, store_id, access_token, account_ids, campaigns):
    from .utils import get_facebook_ads

    user = User.objects.get(pk=user_id)
    store = user.profile.get_shopify_stores().filter(pk=store_id).first()
    try:
        get_facebook_ads(user, store, access_token, account_ids, campaigns)

        store.pusher_trigger('facebook-insights', {
            'success': True
        })
    except Exception:
        raven_client.captureException()

        store.pusher_trigger('facebook-insights', {
            'success': False,
            'error': 'Facebook API Error',
        })
