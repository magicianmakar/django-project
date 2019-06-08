from urllib.parse import urlencode
from http.client import HTTPSConnection

import arrow
from django.conf import settings

page_id = 'h2sbr9ckt5yj'
api_base = 'api.statuspage.io'


def record_import_metric(value):
    metric_id = 'd4zgllcm5n5d'
    ts = arrow.now().timestamp

    if not settings.STATUSPAGE_API_KEY:
        return

    params = urlencode({
        'data[timestamp]': ts,
        'data[value]': value
    })

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "OAuth {}".format(settings.STATUSPAGE_API_KEY)
    }

    conn = HTTPSConnection(api_base)
    conn.request("POST", f"/v1/pages/{page_id}/metrics/{metric_id}/data.json", params, headers)
    conn.getresponse()


def record_aliexpress_single_order(value):
    metric_id = '3z23xpfbbg00'
    ts = arrow.now().timestamp

    if not settings.STATUSPAGE_API_KEY:
        return

    params = urlencode({
        'data[timestamp]': ts,
        'data[value]': value
    })

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"OAuth {settings.STATUSPAGE_API_KEY}"
    }

    conn = HTTPSConnection(api_base)
    conn.request("POST", f"/v1/pages/{page_id}/metrics/{metric_id}/data.json", params, headers)
    conn.getresponse()


def record_aliexpress_multi_order(value):
    metric_id = 'b6jqk3r4bb02'
    ts = arrow.now().timestamp

    if not settings.STATUSPAGE_API_KEY:
        return

    params = urlencode({
        'data[timestamp]': ts,
        'data[value]': value
    })

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"OAuth {settings.STATUSPAGE_API_KEY}"
    }

    conn = HTTPSConnection(api_base)
    conn.request("POST", f"/v1/pages/{page_id}/metrics/{metric_id}/data.json", params, headers)
    conn.getresponse()
