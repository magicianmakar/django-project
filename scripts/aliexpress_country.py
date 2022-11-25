#!/usr/bin/env python

from requests import get
from tqdm import tqdm

import json
import time


def get_response(url):
    tries = 10
    while tries:
        tries -= 1

        try:
            r = get(url, timeout=10)
            return json.loads(r.text.strip()[5:-1])
        except:
            print('Try:', tries)
            time.sleep(tries)


countries = ['AU', 'CL', 'ES', 'NL', 'UA', 'UK', 'NZ', 'US', 'CA', 'RU', 'ID', 'TH', 'PL', 'FR', 'IT', 'TR', 'BR', 'KR', 'SA', 'DE', 'JP']

saved_data = json.loads(open('app/data/shipping/aliexpress_countries.json').read())
for i in countries:
    print('> Country:', i)
    provinces = get_response('https://ilogisticsaddress.aliexpress.com/ajaxGetGlobalAddress.htm?country=%s' % i)
    saved_data[i] = {}

    print('>> Provinces:', len(provinces['address']))
    obar = tqdm(total=len(provinces['address']))
    for p in provinces['address']:
        saved_data[i][p['n']] = []
        province = {
            'name': p['n'],
            'id': p['id'],
            'needChildren': p['needChildren'],
            'cities': []
        }

        obar.update(1)

        if p['needChildren']:
            cities = get_response('https://ilogisticsaddress.aliexpress.com/ajaxGetGlobalAddress.htm?country=%s&province=%s' % (i, p['id']))
            for c in cities['address']:
                saved_data[i][p['n']].append(c['n'])

    out = open('app/data/shipping/aliexpress_countries.json', 'w')
    out.write(json.dumps(saved_data, sort_keys=True, indent=2, separators=(',', ': ')))

    obar.close()
    print()
    print()
