import os
from hashlib import md5

from django.core.cache import cache
from django.conf import settings


def load_uk_provincess():
    for i in ['uk_provinces2.csv', 'uk_provinces.csv']:
        data_file = os.path.join(settings.BASE_DIR, 'app', 'data', i)
        uk_provinces = {}
        lines = open(data_file).readlines()
        for l in lines:
            l = l.split('|')
            if len(l) == 2:
                uk_provinces[l[0].lower().strip()] = l[1].strip()

    return uk_provinces


def missing_province(city):
    city_key = md5(city.lower().strip()).hexdigest()[:8]
    city_key = 'uk_province_{}'.format(city_key)
    if cache.get(city_key) is None:
        print 'WARNING: UK Province not found for:', city
        cache.set(city_key, 1, timeout=3600)
