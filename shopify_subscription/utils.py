import requests
from django.conf import settings


class BaremetricsRequest():
    _base_url = 'https://api.baremetrics.com/v1'
    headers = {
        'Authorization': 'Bearer {}'.format(settings.BAREMETRICS_API_KEY),
        'Accept': 'application/json'
    }

    def __init__(self, source_id=None):
        if source_id:
            self._source_id = source_id

    @property
    def source_id(self):
        if not hasattr(self, '_source_id'):
            self.reload_source_id()

        return self._source_id

    def get_endpoint(self, url=''):
        if url and url[0] != '/':
            url = '/{}'.format(url)

        try:
            url = url.format(source_id=self.source_id)
        except:
            pass

        return '{}{}'.format(self._base_url, url)

    def reload_source_id(self, provider='baremetrics'):
        response = requests.get('{}/sources'.format(self._base_url), headers=self.headers)
        response.raise_for_status()
        for source in response.json().get('sources', []):
            if source.get('provider') == provider:
                self._source_id = source.get('id')
                break

    def get(self, url, *args, **kwargs):
        response = requests.get(self.get_endpoint(url), headers=self.headers, *args, **kwargs)
        response.raise_for_status()
        return response

    def post(self, url, *args, **kwargs):
        response = requests.post(self.get_endpoint(url), headers=self.headers, *args, **kwargs)
        response.raise_for_status()
        return response

    def put(self, url, *args, **kwargs):
        response = requests.put(self.get_endpoint(url), headers=self.headers, *args, **kwargs)
        response.raise_for_status()
        return response
