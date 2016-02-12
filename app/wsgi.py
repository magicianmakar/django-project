"""
WSGI config for app project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/howto/deployment/wsgi/
"""

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

from django.core.wsgi import get_wsgi_application
from whitenoise.django import DjangoWhiteNoise

from django.core.cache.backends.memcached import BaseMemcachedCache

application = get_wsgi_application()
application = DjangoWhiteNoise(application)

# Fix django closing connection to memcached after every request (#11331)
# From https://devcenter.heroku.com/articles/memcachier#django
BaseMemcachedCache.close = lambda self, **kwargs: None
