import json
from unittest.mock import patch

from leadgalaxy.tests.factories import UserFactory

from lib.test import BaseTestCase


class ApiTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.client.login(username=self.user.username, password=self.password)

    @patch('shopified_core.mixins.ApiResponseMixin.get_user')
    def test_post_page(self, get_api_user):
        get_api_user.return_value = self.user

        data = {'page': '<html>test</html>'}
        r = self.client.post('/api/metrics/page', data)

        self.assertEqual(r.status_code, 200)
        rep = json.loads(r.content)
        self.assertIsNotNone(rep.get('id'))
        self.assertIn('page:', rep['id'])
