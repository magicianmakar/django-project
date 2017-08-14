from django.http import HttpResponseRedirect
from django.utils.crypto import get_random_string
from django.views.generic import TemplateView
from django.contrib.auth import login as user_login
from django.contrib import messages
from django.conf import settings
from django.db.models.signals import post_save

import arrow
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import unique_username
from stripe_subscription.stripe_api import stripe
from leadgalaxy.models import User, UserProfile, GroupPlan, userprofile_creation


class PlanCheckoutView(TemplateView):
    template_name = 'checkout.html'

    def get_context_data(self, **kwargs):
        context = super(PlanCheckoutView, self).get_context_data(**kwargs)
        return context

    def post(self, request, *args, **kwargs):
        if request.GET['option'] == '3pay':
            amount = 397
            description = 'Dropified Lifetime Offer - 3 Payment Option'
        else:
            amount = 997
            description = 'Dropified Lifetime Offer - 1 Payment Option'

        error = None

        email = request.POST['stripeEmail']
        username = unique_username(email)

        fullname = request.POST['stripeBillingName'].split(' ')

        n = 1
        while User.objects.filter(username__iexact=username).exists():
            username = '{}{}'.format(username, n)
            n += 1

        created = False

        try:
            user = User.objects.get(email__iexact=email)
            profile = user.profile
        except User.DoesNotExist:
            post_save.disconnect(userprofile_creation, User)
            user = User(
                username=username,
                email=email,
                first_name=fullname[0],
                last_name=u' '.join(fullname[1:]))

            user.set_password(get_random_string(20))
            user.save()

            profile = UserProfile.objects.create(user=user)

            created = True

        try:
            profile.create_stripe_customer(source=request.POST['stripeToken'])

            stripe.Charge.create(
                amount=amount * 100,
                currency="usd",
                customer=user.stripe_customer.customer_id,
                description=description,
            )

        except (stripe.CardError, stripe.InvalidRequestError) as e:
            raven_client.captureException(level='warning')
            error = 'Credit Card Error: {}'.format(e.message)

        except:
            raven_client.captureException()
            error = 'Could not make the purchase'

        if error:
            messages.error(request, error)

            if created:
                profile.delete()
                user.delete()

            return super(PlanCheckoutView, self).get(request, *args, **kwargs)

        profile.change_plan(GroupPlan.objects.get(slug='shopified-app-lifetime-access'))
        profile.set_config_value('lifetime_purchase', request.GET['option'])
        profile.set_config_value('lifetime_charge', arrow.utcnow().timestamp)

        user.backend = settings.AUTHENTICATION_BACKENDS[0]

        user_login(request, user)

        request.session['lead_dyno_record'] = True

        return HttpResponseRedirect('/lifetime/ty')


class LifetimePurchaseThankYouView(TemplateView):
    template_name = 'lifetime_purchase_ty.html'

    def get_context_data(self, **kwargs):
        context = super(LifetimePurchaseThankYouView, self).get_context_data(**kwargs)
        context['lead_dyno_record'] = self.request.session.pop('lead_dyno_record', False)
        return context
