import json
from unittest.mock import patch

from django.urls import reverse

from alibaba_core.models import AlibabaAccount
from leadgalaxy.tests.factories import UserFactory
from lib.test import BaseTestCase


class AccessTokenRedirectViewTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()

        self.client.login(
            username=self.user.username,
            password=self.password
        )

    @patch('alibaba_core.utils.APIRequest.get_response')
    @patch('lib.aliexpress_api.RestApi.getResponse')
    def test_get_redirect_url(self, api_result, mock_response):
        self.assertEqual(AlibabaAccount.objects.count(), 0)

        api_result.return_value = {
            'top_auth_token_create_response': {
                'token_result': json.dumps({
                    "access_token": "test_access_token",
                    "refresh_token": "test_refresh_token",
                    "user_id": "1234567",
                    "expire_time": 1614341945000,
                }),
            }
        }

        message_permit_return_value = {
            "tmc_user_permit_response": {
                "is_success": True
            }
        }

        ecology_token_return_value = {
            'alibaba_dropshipping_token_create_response': {
                'ecology_token': 'test_ecology_token',
            }
        }

        mock_response.side_effect = [
            message_permit_return_value,
            ecology_token_return_value,
        ]
        callback_url = reverse('alibaba:access_token_callback')
        response = self.client.get(f'{callback_url}?code=testcode123')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, '/settings#alibaba-settings')
        self.assertEqual(AlibabaAccount.objects.count(), 1)

        acct = AlibabaAccount.objects.last()
        self.assertEqual(acct.access_token, 'test_access_token')
        self.assertEqual(acct.alibaba_user_id, '1234567')
        self.assertEqual(acct.expired_at.strftime('%b %d, %Y'), 'Feb 26, 2021')
        self.assertEqual(acct.ecology_token, 'test_ecology_token')

    @patch('lib.aliexpress_api.RestApi.getResponse')
    def test_get_redirect_url_error(self, api_result):
        self.assertEqual(AlibabaAccount.objects.count(), 0)

        api_result.return_value = {
            'top_auth_token_create_response': {
                'token_result': '{"error_msg":"Remote service error","sub_code":"isv.param-authorization.code.invalid","error_code":"15"}',
            }
        }
        callback_url = reverse('alibaba:access_token_callback')
        response = self.client.get(f'{callback_url}?code=testcode123')

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, '/settings?code=testcode123')
        self.assertEqual(AlibabaAccount.objects.count(), 0)
