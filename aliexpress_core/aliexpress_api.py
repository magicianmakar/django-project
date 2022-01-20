import re
import socket

from lib.aliexpress_api import RestApi, TopException
from lib.exceptions import capture_exception

from .settings import AFFILIATE_API_KEY, AFFILIATE_API_SECRET, API_KEY, API_SECRET, API_TOKEN


class AliexpressAffiliateApi(RestApi):
    def __init__(self, domain='gw.api.taobao.com', port=80, method='POST', resource=''):
        super().__init__(domain, port)
        self.set_app_info(AFFILIATE_API_KEY, AFFILIATE_API_SECRET)
        self.__apiname = resource
        self.__httpmethod = method

    def getapiname(self):
        return self.__apiname


class AliexpressCategories(AliexpressAffiliateApi):
    def getapiname(self):
        return 'aliexpress.affiliate.category.get'


class AliexpressAffiliateProducts(AliexpressAffiliateApi):
    def getapiname(self):
        return 'aliexpress.affiliate.product.query'


class AliexpressFindAffiliateProduct(AliexpressAffiliateApi):
    def getapiname(self):
        return 'aliexpress.affiliate.productdetail.get'


class AliexpressDropshipApi(RestApi):
    def __init__(self, domain='gw.api.taobao.com', port=80, method='POST', resource=''):
        super().__init__(domain, port)
        self.set_app_info(API_KEY, API_SECRET)
        self.__apiname = resource
        self.__httpmethod = method

    def getapiname(self):
        return self.__apiname


class AliexpressDSRecommendedProducts(AliexpressDropshipApi):
    def getapiname(self):
        return 'aliexpress.ds.recommend.feed.get'


class AliexpressFindDSProduct(AliexpressDropshipApi):
    def getapiname(self):
        return 'aliexpress.ds.product.get'


class APIRequest():
    def __init__(self, access_token=None):
        self.access_token = access_token
        if self.access_token is None:
            self.access_token = API_TOKEN

    def _request(self, api, params=None, remaining_tries=3):
        if remaining_tries < 1:
            return {'error': "AliExpress server is unreachable. Try again later"}

        if params is None:
            params = {}

        for key, value in params.items():
            setattr(api, key, value)

        try:
            return api.getResponse()

        except socket.timeout:
            capture_exception()
            return self._request(api, params=params, remaining_tries=remaining_tries - 1)

        except ConnectionResetError:
            capture_exception()
            return self._request(api, params=params, remaining_tries=remaining_tries - 1)

        except TopException as e:
            capture_exception(extra={
                'errorcode': getattr(e, 'errorcode', None),
                'subcode': getattr(e, 'subcode', None),
                'message': getattr(e, 'message', None),
            })

            if e.errorcode == 7 and 'call limited' in e.message.lower():
                seconds = re.findall(r'(\d+).+?(?=seconds)', e.submsg)
                if seconds:
                    return {'error': f'AliExpress calls limit reached, {seconds[0]} seconds to reset limits'}

            if e.errorcode == 15 and e.subcode == 'isp.top-remote-connection-timeout':
                return self._request(api, params=params, remaining_tries=remaining_tries - 1)

    def get_aliexpress_categories(self, params=None):
        api = AliexpressCategories()

        response = self._request(api, params=params)
        if response.get('error', None):
            return response

        return response['aliexpress_affiliate_category_get_response']['resp_result']

    def affiliate_products(self, params=None):
        api = AliexpressAffiliateProducts()

        response = self._request(api, params=params)
        if response.get('error', None):
            return response

        return response['aliexpress_affiliate_product_query_response']['resp_result']

    def find_ds_product(self, params=None):
        api = AliexpressFindDSProduct()
        api.session = self.access_token

        response = self._request(api, params=params)
        if response.get('error', None):
            return response

        return response['aliexpress_ds_product_get_response']['result']

    def find_affiliate_product(self, params=None):
        api = AliexpressFindAffiliateProduct()

        response = self._request(api, params=params)
        if response.get('error', None):
            return response

        return response['aliexpress_affiliate_productdetail_get_response']['resp_result']

    def ds_recommended_products(self, params=None):
        api = AliexpressDSRecommendedProducts()
        api.session = self.access_token

        response = self._request(api, params=params)
        if response.get('error', None):
            return response

        return response['aliexpress_ds_recommend_feed_get_response']['result']
