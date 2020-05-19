import traceback

from django.conf import settings

from raven.contrib.django.raven_compat.models import client


def capture_exception(*args, **options):
    if settings.DEBUG:
        print('[Capture Exception]:', *args, options)
        traceback.print_exc()

    client.captureException(*args, **options)


def capture_message(*args, **options):
    if settings.DEBUG:
        print('[Capture Message]:', *args, options)

    client.captureMessage(*args, **options)
