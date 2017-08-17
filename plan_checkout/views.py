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
from analytic_events.models import PlanSelectionEvent
from stripe_subscription.models import StripeSubscription
from stripe_subscription.utils import SubscriptionException, subscription_end_trial, update_subscription


class PlanCheckoutView(TemplateView):
    template_name = 'lifetime_checkout.html'

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


class PurchaseThankYouView(TemplateView):
    template_name = 'purchase_ty.html'

    def get_context_data(self, **kwargs):
        context = super(PurchaseThankYouView, self).get_context_data(**kwargs)
        context['lead_dyno_record'] = self.request.session.pop('lead_dyno_record', False)
        context['plan_price'] = kwargs.get('plan_price')

        return context


class MonthlyCheckoutView(TemplateView):
    template_name = 'monthly_checkout.html'

    def get_context_data(self, **kwargs):
        context = super(MonthlyCheckoutView, self).get_context_data(**kwargs)

        print kwargs

        if kwargs['plan_price'] == '47':
            context['monthly_plan'] = 'Elite'
        elif kwargs['plan_price'] == '99':
            context['monthly_plan'] = 'Unlimited'

        context['monthly_price'] = int(kwargs['plan_price'])
        context['ecom_jam'] = kwargs['ecom_jam']

        return context

    def post(self, request, *args, **kwargs):
        if request.GET['option'] == '99':
            plan = GroupPlan.objects.get(slug='unlimited')
        else:
            plan = GroupPlan.objects.get(slug='elite')

        error = None

        email = request.POST['stripeEmail']
        username = unique_username(email)

        fullname = request.POST['stripeBillingName'].split(' ')

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

            user.stripe_customer.can_trial = False
            user.stripe_customer.save()

            sub = stripe.Subscription.create(
                customer=user.stripe_customer.customer_id,
                plan=plan.stripe_plan.stripe_id,
                metadata={'plan_id': plan.id, 'user_id': user.id}
            )

            update_subscription(user, plan, sub)

            if not user.stripe_customer.can_trial:
                try:
                    subscription_end_trial(user, raven_client, delete_on_error=True)

                except SubscriptionException as e:
                    StripeSubscription.objects.filter(subscription_id=sub.id).delete()

                    error = e.message

                except:
                    raven_client.captureException()
                    error = 'Server Error'

            profile = user.profile
            profile.plan = plan
            profile.save()

            PlanSelectionEvent.objects.create(user=user)

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

            return super(MonthlyCheckoutView, self).get(request, *args, **kwargs)

        profile.set_config_value('monthly_subscribe', request.GET['option'])
        profile.set_config_value('monthly_charge', arrow.utcnow().timestamp)

        user.backend = settings.AUTHENTICATION_BACKENDS[0]

        user_login(request, user)

        request.session['lead_dyno_record'] = True

        return HttpResponseRedirect('%s/ty' % request.path)
