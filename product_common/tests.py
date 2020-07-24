from unittest.mock import Mock, patch

from lib.test import BaseTestCase
from product_common.lib.shipstation import get_shipstation_shipments


class ShipstationTestCase(BaseTestCase):
    def setUp(self):
        pass

    @patch('product_common.lib.shipstation.get_paginated_response', return_value=True)
    @patch('product_common.lib.shipstation.get_auth_header')
    @patch('product_common.lib.shipstation.requests.get')
    def test_must_use_correct_api_url(self,
                                      requests_get,
                                      get_auth_header,
                                      get_paginated_response):
        get_auth_header.return_value = {}

        get_shipstation_shipments('http://url?1=1')
        requests_get.assert_called_with(
            'http://url?1=1&pageSize=500',
            headers={'Content-Type': 'application/json'}
        )

        get_shipstation_shipments('http://url?')
        requests_get.assert_called_with(
            'http://url?pageSize=500',
            headers={'Content-Type': 'application/json'}
        )

        get_shipstation_shipments('http://url')
        requests_get.assert_called_with(
            'http://url?pageSize=500',
            headers={'Content-Type': 'application/json'}
        )
