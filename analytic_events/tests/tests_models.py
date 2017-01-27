from django.test import TestCase
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session

from leadgalaxy.tests.factories import UserFactory

from ..models import (
    Event,
    RegistrationEvent,
    PlanSelectionEvent,
    BillingInformationEntryEvent,
    SuccessfulPaymentEvent,
)


class EventTestCase(TestCase):
    def test_must_be_polymorphic(self):
        RegistrationEvent.objects.create(user=UserFactory())
        self.assertEquals(Event.objects.count(), 1)


class RegistrationEventTestCase(TestCase):
    def setUp(self):
        self.registration_event = RegistrationEvent.objects.create(user=UserFactory())

    def test_must_have_facebook_script_after_fire(self):
        self.assertIn(self.registration_event.facebook_script, self.registration_event.fire())

    def test_must_have_google_analytics_script_after_fire(self):
        self.assertIn(self.registration_event.google_analytics_script, self.registration_event.fire())

    def test_must_have_mixpanel_script_after_fire(self):
        self.assertIn(self.registration_event.mixpanel_script, self.registration_event.fire())


class PlanSelectionEventTestCase(TestCase):
    def setUp(self):
        self.plan_selection_event = PlanSelectionEvent.objects.create(user=UserFactory())

    def test_must_have_facebook_script_after_fire(self):
        self.assertIn(self.plan_selection_event.facebook_script, self.plan_selection_event.fire())

    def test_must_have_google_analytics_script_after_fire(self):
        self.assertIn(self.plan_selection_event.google_analytics_script, self.plan_selection_event.fire())

    def test_must_have_mixpanel_script_after_fire(self):
        self.assertIn(self.plan_selection_event.mixpanel_script, self.plan_selection_event.fire())


class BillingInformationEntryEventTestCase(TestCase):
    def setUp(self):
        source = '{}'
        self.billing_event = BillingInformationEntryEvent.objects.create(user=UserFactory(), source=source)

    def test_must_have_facebook_script_after_fire(self):
        self.assertIn(self.billing_event.facebook_script, self.billing_event.fire())

    def test_must_have_google_analytics_script_after_fire(self):
        self.assertIn(self.billing_event.google_analytics_script, self.billing_event.fire())

    def test_must_have_mixpanel_script_after_fire(self):
        self.assertIn(self.billing_event.mixpanel_script, self.billing_event.fire())


class SuccessfulPaymentEventTestCase(TestCase):
    def setUp(self):
        charge = '{}'
        self.payment_event = SuccessfulPaymentEvent.objects.create(user=UserFactory(), charge=charge)

    def test_must_have_facebook_script_after_fire(self):
        self.assertIn(self.payment_event.facebook_script, self.payment_event.fire())

    def test_must_have_google_analytics_script_after_fire(self):
        self.assertIn(self.payment_event.google_analytics_script, self.payment_event.fire())

    def test_must_have_mixpanel_script_after_fire(self):
        self.assertIn(self.payment_event.mixpanel_script, self.payment_event.fire())
