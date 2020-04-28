import requests


class ShopifyAPI:
    store = None
    version = '2020-04'

    _pagination_limit = 240

    def __init__(self, store=None):
        self.store = store

    def get_orders(self, params, page_info=None):
        links, data = self._get_resource(
            resource='orders',
            params=params,
            page_info=page_info,
            raise_for_status=True)

        if links.get('next'):
            next_page_info = links['next']['url']
        else:
            next_page_info = None

        if links.get('previous'):
            previous_page_info = links['previous']['url']
        else:
            previous_page_info = None

        return data['orders'], next_page_info, previous_page_info

    def get_orders_count(self, params):
        links, data = self._get_resource(
            resource='orders/count',
            params=params,
            raise_for_status=True)

        return data['count']

    def recurring_charges(self, params={}, active=False):
        links, data = self._get_resource(
            resource='recurring_application_charges',
            params=params,
            raise_for_status=True)

        charges = data['recurring_application_charges']

        if active:
            charges = [c for c in charges if c['status'] == 'active']

        return charges

    def application_charges(self, params={}, active=False):
        links, data = self._get_resource(
            resource='application_charges',
            params=params,
            raise_for_status=True)

        charges = data['application_charges']

        if active:
            charges = [c for c in charges if c['status'] == 'active']

        return charges

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
        next_page_info = None
        first_page = True
        while first_page or next_page_info:
            links, rep = self._get_resource(resource=resource, params=params, page_info=next_page_info)

            if links.get('next'):
                next_page_info = links['next']['url']
            else:
                next_page_info = None

            first_page = False

            yield rep[resource]

    def _get_resource(self, resource, params, page_info=None, raise_for_status=False):
        tries = 3
        while tries:
            if not page_info:
                rep = requests.get(url=self.store.api(resource, version=self.version), params=params)
            else:
                rep = requests.get(url=self.store.api(page_info, version=self.version))

            if rep.ok:
                break
            else:
                tries -= 1

        if raise_for_status:
            rep.raise_for_status()

        return rep.links, rep.json()
