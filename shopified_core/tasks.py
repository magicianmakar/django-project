from __future__ import absolute_import

import requests
from django.conf import settings
from django.core.mail import send_mail

from app.celery import celery_app, CaptureFailure

from raven.contrib.django.raven_compat.models import client as raven_client


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def send_email_async(self, **kwargs):
    try:
        send_mail(**kwargs)
    except:
        raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_intercom_tags(self, email, attribute_id, attribute_value):
    if settings.INTERCOM_ACCESS_TOKEN:
        headers = {
            'Authorization': 'Bearer {}'.format(settings.INTERCOM_ACCESS_TOKEN),
            'Accept': 'application/json'
        }
        url = 'https://api.intercom.io/users'

        data = {
            "email": email,
            "custom_attributes": {
                attribute_id: attribute_value
            }
        }
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
        except:
            raven_client.captureException()


@celery_app.task(base=CaptureFailure, bind=True, ignore_result=True)
def update_baremetrics_attributes(self, email, attribute_id, attribute_value):
    if settings.BAREMETRICS_API_KEY:
        headers = {
            'Authorization': 'Bearer {}'.format(settings.BAREMETRICS_API_KEY),
            'Accept': 'application/json'
        }
        url = 'https://api.baremetrics.com/v1/attributes'
        data = {
            "attributes": [{
                "customer_email": email,
                "field_id": attribute_id,
                "value": attribute_value
            }]
        }

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
        except:
            raven_client.captureException()
