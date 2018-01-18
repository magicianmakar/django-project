import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings

PRICE_MONITOR_BASE = '{}/api'.format(settings.PRICE_MONITOR_HOSTNAME)


def aliexpress_variants(product_id):
    variants_api_url = '{}/products/{}/variants'.format(PRICE_MONITOR_BASE, product_id)
    rep = requests.get(
        url=variants_api_url,
        auth=HTTPBasicAuth(settings.PRICE_MONITOR_USERNAME, settings.PRICE_MONITOR_PASSWORD)
    )
    rep.raise_for_status()
    return rep.json()
