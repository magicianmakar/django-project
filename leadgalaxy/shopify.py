import requests


class ShopifyAPI:
    store = None
    version = '2020-04'

    _pagination_limit = 240

    def __init__(self, store=None):
        self.store = store

    def paginate_orders(self, **kwargs):
        defaults = {
            'limit': self._pagination_limit,
            'status': 'any',
            'fulfillment': 'any',
            'financial': 'any'
        }

        for key, val in defaults.items():
            if key not in kwargs:
                kwargs[key] = val

        if kwargs.get('ids'):
            if type(kwargs['ids']) is list:
                kwargs['ids'] = ','.join([str(n) for n in kwargs['ids']])

        yield from self.paginate_resource('orders', params=kwargs)

    def paginate_products(self, **kwargs):
        defaults = {
            'limit': self._pagination_limit,
        }

        for key, val in defaults.items():
            if key not in kwargs:
                kwargs[key] = val

        yield from self.paginate_resource('products', params=kwargs)

    def paginate_resource(self, resource, params):
        next_page_url = None
        first_page = True
        while first_page or next_page_url:
            links, rep = self._get_resource(resource=resource, params=params, page_url=next_page_url)

            if links.get('next'):
                next_page_url = links['next']['url']
            else:
                next_page_url = None

            first_page = False

            yield rep[resource]

    def _get_resource(self, resource, params, page_url):
        if not page_url:
            rep = requests.get(url=self.store.api(resource, version=self.version), params=params)
        else:
            rep = requests.get(url=self.store.api(page_url, version=self.version))

        return rep.links, rep.json()
