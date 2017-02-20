from __future__ import absolute_import

import os
from celery import Celery
from celery import Task

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')

from django.conf import settings
from raven.contrib.django.raven_compat.models import client as raven_client
from raven.contrib.celery import register_signal


app = Celery('shopified')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# hook into the Celery error handler
if hasattr(settings, 'RAVEN_CONFIG'):
    register_signal(raven_client)


class CaptureFailure(Task):
    abstract = True

    def after_return(self, *args, **kwargs):
        raven_client.context.clear()
