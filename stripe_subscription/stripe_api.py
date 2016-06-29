from django.conf import settings

import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY
