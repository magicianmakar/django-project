import hmac
import hashlib

from django.core.cache import cache
from django.conf import settings

import arrow


def extra_bundles(request):
    """ Extra bundles link """

    if not request.user.is_authenticated():
        return {'extra_bundle': None}

    extra_cache_key = 'extra_bundle_{}'.format(request.user.id)
    extra_bundle = cache.get(extra_cache_key)

    if extra_bundle is None:
        profile = request.user.profile
        bundles = profile.bundles.all().values_list('register_hash', flat=True)
        if profile.plan.register_hash == '5427f85640fb78728ec7fd863db20e4c':  # JVZoo Pro Plan
            if 'b961a2a0f7101efa5c79b8ac80b75c47' not in bundles:  # JVZoo Elite Bundle
                extra_bundle = {'url': 'http://www.shopifiedapp.com/elite', 'title': 'Add Elite Bundle'}
            elif '2fba7df0791f67b61581cfe37e0d7b7d' not in bundles:  # JVZoo Unlimited
                extra_bundle = {'url': 'http://www.shopifiedapp.com/unlimited', 'title': 'Add Unlimited Bundle'}
            else:
                extra_bundle = False

            cache.set(extra_cache_key, extra_bundle, timeout=900)

        elif profile.plan.register_hash == 'c0dee42b84c736bb62c61ad0f20b9f53':  # Free Plan for Promote Labs
            extra_bundle = {
                'url': 'http://www.shopifiedapp.com/unlimited',
                'title': 'Upgrade To All Drop Shipping Features'
            }

        elif profile.plan.is_stripe() and request.user.have_stripe_billing():
            from stripe_subscription.utils import eligible_for_trial_coupon, trial_coupon_offer_end
            customer = request.user.stripe_customer
            if not customer.have_source() and eligible_for_trial_coupon(customer.get_data()):
                from stripe_subscription.stripe_api import stripe
                from stripe_subscription.utils import format_coupon
                from django.conf import settings

                coupon_key = 'stripe_coupon_{}'.format(settings.STRIP_TRIAL_DISCOUNT_COUPON)
                coupon = cache.get(coupon_key)
                if coupon is None:
                    coupon = stripe.Coupon.retrieve(settings.STRIP_TRIAL_DISCOUNT_COUPON).to_dict()
                    cache.set(coupon_key, coupon, timeout=3600)

                msg = ('Enter your credit card information today and get <b>{}</b><br/>'
                       'You will not be charged until your 14 days Free Trial has ended.<br/><br/>'
                       'This offer will end in <b>{}</b>').format(
                    format_coupon(coupon), trial_coupon_offer_end(customer.get_data()))

                extra_bundle = {
                    'url': '/user/profile#billing',
                    'title': 'Get {}'.format(format_coupon(coupon)),
                    'attrs': 'qtip-tooltip="{}" xqtip-my="" xqtip-at=""'.format(msg),
                    'message': msg,
                    'sametab': True
                }

                cache.set(extra_cache_key, extra_bundle, timeout=3600)

            elif not customer.have_source():
                subscription = request.user.stripesubscription_set.first()
                if subscription:
                    status = subscription.get_status()
                    if status.get('status') == 'trialing':
                        msg = ('Hurry! Your <b>Free {}</b>. Enter your billing '
                               'information to avoid being transported '
                               'back to the Stone Age! :)').format(status.get('status_str'))

                        extra_bundle = {
                            'url': '/user/profile#billing',
                            'title': 'Activate Shopified App Account',
                            'attrs': 'qtip-tooltip="{}" xqtip-my="" xqtip-at=""'.format(msg),
                            'message': msg,
                            'sametab': True
                        }

                        cache.set(extra_cache_key, extra_bundle, timeout=3600)

        elif (profile.plan.is_free or profile.plan.is_stripe()) and request.user.stripe_customer.can_trial:
            extra_bundle = {
                'url': '/user/profile#plan',
                'title': 'Start Your 14 Days Free Trial!',
                'sametab': True
            }

            cache.set(extra_cache_key, extra_bundle, timeout=3600)

    # Terms of Service update message
    # 2016-08-24 is the date of adding agree to TOS before registering
    tos_update = not request.user.get_config('_tos-update') and \
        arrow.get('2016-08-24').datetime > request.user.date_joined

    return {
        'extra_bundle': extra_bundle,
        'tos_update': tos_update,
    }


def extension_release(request):
    return {
        'DEBUG': settings.DEBUG,
        'extension_release': cache.get('extension_release'),
        'extension_required': cache.get('extension_required')
    }


def intercom(request):
    ctx = {
        'INTERCOM_APP_ID': settings.INTERCOM_APP_ID
    }

    if request.user.is_authenticated() and settings.INTERCOM_SECRET_KEY:
        ctx['INTERCOM_USER_HASH'] = hmac.new(settings.INTERCOM_SECRET_KEY,
                                             str(request.user.id),
                                             hashlib.sha256).hexdigest()

    return ctx


def facebook_pixel(request):
    return {
        'FACEBOOK_PIXEL_ID': settings.FACEBOOK_PIXEL_ID
    }
