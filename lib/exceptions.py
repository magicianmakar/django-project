import traceback
import sys

from django.conf import settings

from raven.contrib.django.raven_compat.models import client


def capture_exception(*args, **options):
    if settings.DEBUG or 'test' in sys.argv:
        print()
        print('------> Capture Exception')
        print('------>')

        if args:
            print('------> args:', *args)

        if options:
            print('------> options:', options)

        print('------>')
        for line in traceback.format_exc().split('\n'):
            print(f'------> {line}')
        print('------>')

    client.captureException(*args, **options)


def capture_message(*args, **options):
    if settings.DEBUG or 'test' in sys.argv:
        print()
        print('------> Capture Message')
        print('------>')

        if args:
            print('------> args:', *args)

        if options:
            print('------> options:', options)

        print('------>')

    client.captureMessage(*args, **options)
