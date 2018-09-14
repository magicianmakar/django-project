from __future__ import absolute_import

import os
import random

from celery import Celery
from celery import Task

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

from django.conf import settings
from django.core.cache import cache
from raven.contrib.django.raven_compat.models import client as raven_client
from raven.contrib.celery import register_signal


celery_app = Celery('shopified')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
celery_app.config_from_object('django.conf:settings')
celery_app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# hook into the Celery error handler
if hasattr(settings, 'RAVEN_CONFIG'):
    register_signal(raven_client)


class CaptureFailure(Task):
    abstract = True

    def after_return(self, *args, **kwargs):
        raven_client.context.clear()


def retry_countdown(key, retries):
    retries = max(1, retries)
    countdown = cache.get(key, random.randint(10, 30)) + random.randint(retries, retries * 60) + (60 * retries)
    cache.set(key, countdown + random.randint(5, 30), timeout=countdown + 60)

    return countdown


def api_exceed_limits_countdown(key):
    """
    Returns exponentially increased countdown
    """
    call_count = cache.get(key, 0) + 1
    cache.set(key, call_count, timeout=20)
    countdown = sum(range(call_count)) * random.randint(10, 30)

    return countdown if countdown < 3000 else 3000
