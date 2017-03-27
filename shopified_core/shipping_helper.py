import os
import simplejson as json
from hashlib import md5
from collections import OrderedDict

from django.core.cache import cache
from django.conf import settings


uk_provinces = None
countries_code = None
provinces_code = {}


def load_uk_provincess():
    global uk_provinces

    if uk_provinces:
        return uk_provinces

    uk_provinces = {}
    for i in ['uk_provinces2.csv', 'uk_provinces.csv']:
        data_file = os.path.join(settings.BASE_DIR, 'app', 'data', i)
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


def load_countries():
    global countries_code

    if countries_code is None:
        countries_code = json.load(
            open(os.path.join(settings.BASE_DIR, 'app/data/shipping/countries.json')),
            object_pairs_hook=OrderedDict)

    return countries_code


def get_counrties_list():
    return load_countries().items()


def country_from_code(country_code, default=None):
    countries = load_countries()

    if default is not None:
        return countries.get(country_code, default)
    else:
        return countries[country_code]


def province_from_code(country_code, province_code):
    global countries_code

    country_code = country_code.lower()
    if country_code not in provinces_code:
        path = os.path.join(settings.BASE_DIR, 'app/data/shipping/provinces/{}.json'.format(country_code))
        if os.path.isfile(path):
            provinces_code[country_code] = json.load(open(path))

    province = provinces_code.get(country_code, {}).get(province_code)

    return province if province else province_code
