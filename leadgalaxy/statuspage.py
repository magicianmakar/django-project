import httplib
import urllib

import arrow

from django.conf import settings

page_id = 'h2sbr9ckt5yj'
api_base = 'api.statuspage.io'


def record_import_metric(value):
    metric_id = 'd4zgllcm5n5d'
    ts = arrow.now().timestamp

    if not settings.STATUSPAGE_API_KEY:
        return

    params = urllib.urlencode({
        'data[timestamp]': ts,
        'data[value]': value
    })

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": "OAuth {}".format(settings.STATUSPAGE_API_KEY)
    }

    conn = httplib.HTTPSConnection(api_base)
    conn.request("POST", "/v1/pages/{}/metrics/{}/data.json".format(page_id, metric_id), params, headers)
    print conn.getresponse()
