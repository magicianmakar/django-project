from django.contrib.auth.models import User

from raven.contrib.django.raven_compat.models import client as raven_client
from app.celery import celery_app, CaptureFailure

from affiliations.utils import LeadDynoAffiliations, LeadDynoAffiliation


@celery_app.task(bind=True, base=CaptureFailure)
def create_lead_dyno_affiliation(self, user_id):
    try:
        user = User.objects.get(pk=user_id)

        affiliation = LeadDynoAffiliation(user)
        affiliation.check_affiliation()
    except:
        raven_client.captureException()


@celery_app.task(bind=True, base=CaptureFailure)
def sync_lead_dyno_resources(self):
    affiliations = LeadDynoAffiliations()
    try:
        affiliations.sync()
        affiliations.finish_sync()

    except Exception:
        raven_client.captureException()
