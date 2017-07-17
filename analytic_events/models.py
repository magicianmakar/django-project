import simplejson as json

from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils.functional import cached_property

from polymorphic.models import PolymorphicModel

from leadgalaxy.models import ENTITY_STATUS_CHOICES


class Event(PolymorphicModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def fire(self):
        scripts = self.get_scripts()
        if self.pk:
            Event.objects.filter(pk=self.pk).delete()

        return scripts

    def get_scripts(self):
        raise NotImplementedError('All event subclasses must implement this method.')


class RegistrationEvent(Event):

    def get_scripts(self):
        return ''.join([self.facebook_script,
                        self.google_analytics_script,
                        self.mixpanel_script])

    def get_data(self):
        stripe_plan = getattr(self.user.profile.plan, 'stripe_plan', None)
        amount = float(stripe_plan.amount) if stripe_plan else 0

        return {'username': self.user.username,
                'email': self.user.email,
                'plan': getattr(self.user.profile.plan, 'title', ''),
                'value': amount,
                'currency': 'USD',
                'status': dict(ENTITY_STATUS_CHOICES).get(self.user.profile.status, '')}

    @cached_property
    def facebook_script(self):
        event_data = self.get_data()
        data = {'value': event_data.get('value'),
                'currency': event_data.get('currency'),
                'status': event_data.get('status'),
                'content_name': event_data.get('plan')}

        return "<script>fbq('track', 'CompleteRegistration', %s);</script>" % json.dumps(data)

    @cached_property
    def google_analytics_script(self):
        event_data = self.get_data()
        data = {'eventCategory': 'User Actions',
                'eventAction': 'Register',
                'eventLabel': event_data.get('plan'),
                'eventValue': round(event_data.get('value', 0))}

        data = json.dumps(data)

        return '''<script>
            ga('send', 'event', {0});
            ga('clientTracker.send', 'event', {0});
            </script>'''.format(data)

    @cached_property
    def mixpanel_script(self):
        return "<script>mixpanel.track('Registered', %s);</script>" % json.dumps(self.get_data())


class PlanSelectionEvent(Event):

    def get_scripts(self):
        return ''.join([self.facebook_script,
                        self.google_analytics_script,
                        self.mixpanel_script])

    def get_data(self):
        plan = self.user.profile.plan
        stripe_plan = getattr(plan, 'stripe_plan', None)
        amount = float(stripe_plan.amount) if stripe_plan else 0

        return {'username': self.user.username,
                'email': self.user.email,
                'plan': plan.title,
                'amount': amount}

    @cached_property
    def facebook_script(self):
        event_data = self.get_data()
        data = {'value': event_data['amount'],
                'currency': 'USD',
                'content_name': event_data['plan']}

        return "<script>fbq('track', 'AddToCart', %s);</script>" % json.dumps(data)

    @cached_property
    def google_analytics_script(self):
        data = {'eventCategory': 'User Actions', 'eventAction': 'Select Plan'}

        data = json.dumps(data)

        return '''<script>
            ga('send', 'event', {0});
            ga('clientTracker.send', 'event', {0});
            </script>'''.format(data)

    @cached_property
    def mixpanel_script(self):
        return "<script>mixpanel.track('Plan Selected', %s);</script>" % json.dumps(self.get_data())


class BillingInformationEntryEvent(Event):
    source = models.TextField()

    def get_scripts(self):
        return ''.join([self.facebook_script,
                        self.google_analytics_script,
                        self.mixpanel_script])

    def get_data(self):
        data = json.loads(self.source)
        data['username'] = self.user.username
        data['email'] = self.user.email

        return data

    @cached_property
    def facebook_script(self):
        data = {'value': 0, 'currency': 'USD'}

        return "<script>fbq('track', 'AddPaymentInfo', %s);</script>" % json.dumps(data)

    @cached_property
    def google_analytics_script(self):
        data = {'eventCategory': 'User Actions', 'eventAction': 'Entered Billing Information'}
        data = json.dumps(data)

        return '''<script>
            ga('send', 'event', {0});
            ga('clientTracker.send', 'event', {0});
            </script>'''.format(data)

    @cached_property
    def mixpanel_script(self):
        return "<script>mixpanel.track('Entered Billing Information', %s);</script>" % json.dumps(self.get_data())


class SuccessfulPaymentEvent(Event):
    charge = models.TextField()

    def get_scripts(self):
        return ''.join([self.facebook_script,
                        self.google_analytics_script,
                        self.mixpanel_script])

    def get_data(self):
        data = json.loads(self.charge)
        data['username'] = self.user.username

        return data

    @cached_property
    def facebook_script(self):
        event_data = self.get_data()
        value = str(event_data.get('amount', 0) * Decimal('0.01'))
        data = {'value': value, 'currency': 'USD'}

        return "<script>fbq('track', 'Purchase', %s);</script>" % json.dumps(data)

    @cached_property
    def google_analytics_script(self):
        data = {'eventCategory': 'User Actions', 'eventAction': 'Successful Payment'}

        data = json.dumps(data)

        return '''<script>
            ga('send', 'event', {0});
            ga('clientTracker.send', 'event', {0});
            </script>'''.format(data)

    @cached_property
    def mixpanel_script(self):
        return "<script>mixpanel.track('Successful Payment', %s);</script>" % json.dumps(self.get_data())
