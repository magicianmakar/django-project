import traceback
import sys

from django.conf import settings

from raven.contrib.django.raven_compat.models import client


def capture_exception(*args, **options):
    e_type, e, _ = sys.exc_info()
    if hasattr(e, 'response') and hasattr(e.response, 'text'):
        try:
            extra = options.get('extra', {})
            extra['response_text'] = e.response.text
            extra['response_status'] = e.response.status_code
            extra['response_reason'] = e.response.reason

            options['extra'] = extra
        except Exception:
            pass

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

        if e:
            print('------> Type:', e_type)
            if hasattr(e, 'message'):
                print('------> Exception message:', e.message)

            if hasattr(e, 'response') and hasattr(e.response, 'text'):
                print('------> Exception response:', e.response.text)

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
