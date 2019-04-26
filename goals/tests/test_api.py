import json

from leadgalaxy.tests.factories import UserFactory
from lib.test import BaseTestCase
from ..models import Step
from .. import step_slugs


class ExtensionIsInstalledTestcase(BaseTestCase):
    def setUp(self):
        self.endpoint = '/api/goals/extension-is-installed'
        self.slug = step_slugs.INSTALL_CHROME_EXTENSION
        self.username = 'test'
        self.user = UserFactory(username=self.username)
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

    def test_must_update_user_completed_steps_if_extension_is_installed(self):
        step = Step.objects.get(slug=self.slug)
        self.client.login(username=self.username, password=self.password)
        self.client.post(self.endpoint)
        self.assertTrue(self.user.completed_steps.filter(pk=step.pk).exists())

    def test_must_return_slug_if_step_is_added_to_user(self):
        self.client.login(username=self.username, password=self.password)
        r = self.client.post(self.endpoint)
        data = json.loads(r.content)
        self.assertEqual(self.slug, data['slug'])

    def test_must_return_true_if_step_is_added_to_user(self):
        self.client.login(username=self.username, password=self.password)
        r = self.client.post(self.endpoint)
        data = json.loads(r.content)
        self.assertTrue(data['added'])

    def test_must_return_false_if_step_is_not_added_to_user(self):
        step = Step.objects.get(slug=self.slug)
        self.user.completed_steps.add(step)
        self.client.login(username=self.username, password=self.password)
        r = self.client.post(self.endpoint)
        data = json.loads(r.content)
        self.assertFalse(data['added'])
