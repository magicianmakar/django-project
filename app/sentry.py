import json
import re

from raven.processors import Processor
from raven.contrib.django.client import DjangoClient


class SentryClient(DjangoClient):
    def __init__(self, *args, **kwargs):
        kwargs['enable_breadcrumbs'] = False
        DjangoClient.__init__(self, *args, **kwargs)


class SentryDataProcessor(Processor):
    def get_data(self, data, **kwargs):
        if 'exception' in data:
            if 'values' in data['exception']:
                for value in data['exception'].get('values', []):
                    if 'value' in value:
                        value['value'] = self.sentitize_urls(value['value'])

                    if 'stacktrace' in value:
                        value['stacktrace'] = self._filter_stacktrace(value['stacktrace'])

        return data

    def _filter_stacktrace(self, data):
        for idx, frame in enumerate(data['frames']):
            if frame.get('vars'):
                if frame['vars'].get('exc'):
                    data['frames'][idx]['vars']['exc'] = self.sentitize_urls(frame['vars']['exc'])
                if frame['vars'].get('http_error_msg'):
                    data['frames'][idx]['vars']['http_error_msg'] = self.sentitize_urls(frame['vars']['http_error_msg'])

        return data

    def sentitize_urls(self, url):
        return re.sub(r'//[^:]*:[^:]+@', '//*:*@', url)
