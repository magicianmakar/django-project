#!/usr/bin/env python

from requests import get
from tqdm import tqdm

import json

countries = ['AU', 'CL', 'ES', 'NL', 'UA', 'UK', 'NZ', 'US', 'CA', 'RU', 'ID', 'TH', 'PL', 'FR']

data = {}
for i in countries:
    print('> Country:', i)
    r = get('https://ilogisticsaddress.aliexpress.com/ajaxGetGlobalAddress.htm?country=%s' % i)
    provinces = json.loads(r.text.strip()[5:-1])
    data[i] = {}

    print('>> Provinces:', len(provinces['address']))
    obar = tqdm(total=len(provinces['address']))
    for p in provinces['address']:
        data[i][p['n']] = []
        province = {
            'name': p['n'],
            'id': p['id'],
            'needChildren': p['needChildren'],
            'cities': []
        }

        obar.update(1)

        if p['needChildren']:
            r = get('https://ilogisticsaddress.aliexpress.com/ajaxGetGlobalAddress.htm?country=%s&province=%s' % (i, p['id']))
            cities = json.loads(r.text.strip()[5:-1])
            for c in cities['address']:
                data[i][p['n']].append(c['n'])

    obar.close()
    print()
    print()

data = json.dumps(data, sort_keys=True, indent=2, separators=(',', ': '))
out = open('app/data/shipping/aliexpress_countries.json', 'w')
out.write(data)
