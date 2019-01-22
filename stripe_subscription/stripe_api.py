from django.conf import settings

import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = '2015-10-16'
