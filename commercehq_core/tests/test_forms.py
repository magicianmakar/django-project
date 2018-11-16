from urlparse import urlparse

from lib.test import BaseTestCase

from leadgalaxy.tests.factories import UserFactory

from ..forms import CommerceHQStoreForm


class CommerceHQStoreFormTestCase(BaseTestCase):
    def setUp(self):
        self.user = UserFactory(username='test')
        self.data = {
            'title': 'Test Store',
            'api_url': 'https://example.commercehq.com',
            'api_key': 'testkey',
            'api_password': 'testpassword'}

    def test_must_accept_commercehq_urls_only(self):
        self.data['api_url'] = 'http://example.com'
        form = CommerceHQStoreForm(self.data)
        self.assertFalse(form.is_valid())

    def test_must_change_scheme_to_https(self):
        self.data['api_url'] = 'http://example.commercehq.com'
        form = CommerceHQStoreForm(self.data)
        store = form.save(commit=False)
        store.user = self.user
        store.save()
        o = urlparse(store.api_url)
        self.assertEquals(o.scheme, 'https')
