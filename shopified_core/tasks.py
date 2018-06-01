from __future__ import absolute_import

from django.core.mail import send_mail

from app.celery import celery_app, CaptureFailure

from raven.contrib.django.raven_compat.models import client as raven_client


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def send_email_async(self, **kwargs):
    try:
        send_mail(**kwargs)
    except:
        raven_client.captureException()
