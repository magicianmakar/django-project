from django.urls import reverse

from leadgalaxy.tests import factories as f
from leadgalaxy.models import AppPermission
from stripe_subscription.models import CustomStripePlan
from lib.test import BaseTestCase


class CallflexPermissionsTestCase(BaseTestCase):
    fixtures = ['callflex_permissions.json']

    def setUp(self):
        pass

    def test_pemissions(self):
        self.assertTrue(AppPermission.objects.filter(name='phone_automation.use').exists())
        self.assertTrue(AppPermission.objects.filter(name='phone_automation_unlimited_phone_numbers.use').exists())
        self.assertTrue(AppPermission.objects.filter(name='phone_automation_unlimited_calls.use').exists())
        self.assertTrue(AppPermission.objects.filter(name='phone_automation_free_number.use').exists())


class CallflexViewsTestCase(BaseTestCase):
    fixtures = ['custom_stripe_plan.json']

    def setUp(self):
        self.user = f.UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)

        self.user.save()

        self.user.profile.plan = f.GroupPlanFactory()
        self.user.profile.plan.permissions.add(f.AppPermissionFactory(name='phone_automation.use', description=''))
        self.user.profile.save()

    def test_dashboard(self):
        path = reverse('phone_automation_index')
        response = self.client.get(path)
        self.assertRedirects(response, '%s?next=%s' % (reverse('login'), path))

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_provision(self):
        path = reverse('phone_automation_provision')
        response = self.client.get(path)
        self.assertRedirects(response, '%s?next=%s' % (reverse('login'), path))

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(reverse('phone_automation_provision'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="provision-phone-number"')

    def test_companies(self):
        path = reverse('phone_automation_companies_index')
        response = self.client.get(path)
        self.assertRedirects(response, '%s?next=%s' % (reverse('login'), path))

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_calllogs(self):
        path = reverse('phone_automation_call_logs')
        response = self.client.get(path)
        self.assertRedirects(response, '%s?next=%s' % (reverse('login'), path))

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_reports(self):
        path = reverse('phone_automation_reports_numbers')
        response = self.client.get(path)
        self.assertRedirects(response, '%s?next=%s' % (reverse('login'), path))

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

        self.client.logout()
        path = reverse('phone_automation_reports_companies')
        response = self.client.get(path)
        self.assertRedirects(response, '%s?next=%s' % (reverse('login'), path))

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_notifications(self):
        path = reverse('phone_automation_notifications_alerts')
        response = self.client.get(path)
        self.assertRedirects(response, '%s?next=%s' % (reverse('login'), path))

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

        self.client.logout()
        path = reverse('phone_automation_notifications_summaries')
        response = self.client.get(path)
        self.assertRedirects(response, '%s?next=%s' % (reverse('login'), path))

        self.client.login(username=self.user.username, password=self.password)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_plans_fixture(self):
        self.assertTrue(CustomStripePlan.objects.count())
