import os
import re
import simplejson as json
import requests

from collections import OrderedDict
from unidecode import unidecode
from fuzzyset import FuzzySet

from django.conf import settings
from django.core.cache import cache

from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import hash_list

uk_provinces = None
aliexpress_countries = None
ebay_countries = None
countries_code = None
provinces_code = {}

ALIEXPRESS_UK_PROVINCES = [
    "aberdeenshire", "angus", "argyll", "avon", "ayrshire", "banffshire", "bedfordshire", "berkshire", "berwickshire", "buckinghamshire",
    "caerphilly", "caithness", "cambridgeshire", "cardiff", "carmarthenshire", "cheshire", "clackmannanshire", "cleveland", "clwyd", "cornwall",
    "county antrim", "county armagh", "county down", "county durham", "county fermanagh", "county londonderry", "county tyrone", "cumbria",
    "derbyshire", "devon", "dorset", "dumfriesshire", "dunbartonshire", "dyfed", "east lothian", "east sussex", "essex", "fife", "glasgow",
    "gloucestershire", "greater manchester", "guernsey", "gwent", "gwynedd", "hampshire", "herefordshire", "hertfordshire", "inverness-shire",
    "isle of arran", "isle of barra", "isle of benbecula", "isle of bute", "isle of canna", "isle of coll", "isle of colonsay", "isle of cumbrae",
    "isle of eigg", "isle of gigha", "isle of harris", "isle of iona", "isle of islay", "isle of jura", "isle of lewis", "isle of mull",
    "isle of north uist", "isle of rum", "isle of scalpay", "isle of skye", "isle of south uist", "isle of tiree", "isle of wight", "isles of scilly",
    "jersey", "kent", "kincardineshire", "kinross-shire", "kirkcudbrightshire", "lanarkshire", "lancashire", "leicestershire", "lincolnshire",
    "london", "merseyside", "mid glamorgan", "middlesex", "midlothian", "morayshire", "nairnshire", "newport", "norfolk", "north humberside",
    "north yorkshire", "northamptonshire", "northumberland", "nottinghamshire", "orkney isles", "oxfordshire", "peeblesshire", "pembrokeshire",
    "perthshire", "powys", "renfrewshire", "ross-shire", "roxburghshire", "rutland", "selkirkshire", "shetland islands", "shropshire", "somerset",
    "south glamorgan", "south humberside", "south yorkshire", "staffordshire", "stirlingshire", "suffolk", "surrey", "sutherland", "tyne and wear",
    "warwickshire", "west glamorgan", "west lothian", "west midlands", "west sussex", "west yorkshire", "wigtownshire", "wiltshire", "worcestershire"
]

ALIEXPRESS_UK_COUNTRIES = {
    "england": [
        'avon', 'bedfordshire', 'berkshire', 'buckinghamshire', 'cambridgeshire', 'cheshire', 'cleveland', 'cornwall', 'county durham', 'cumbria',
        'derbyshire', 'devon', 'dorset', 'east sussex', 'essex', 'gloucestershire', 'greater manchester', 'manchester', 'hampshire', 'herefordshire',
        'hertfordshire', 'isle of wight', 'wight', 'isles of scilly', 'scilly', 'kent', 'lancashire', 'leicestershire', 'lincolnshire', 'london',
        'greater london' 'merseyside', 'middlesex', 'norfolk', 'north humberside', 'north yorkshire', 'northamptonshire', 'northumberland',
        'nottinghamshire', 'oxfordshire', 'rutland', 'shropshire', 'somerset', 'south humberside', 'south yorkshire', 'staffordshire', 'suffolk',
        'surrey', 'tyne and wear', 'warwickshire', 'west midlands', 'west sussex', 'west yorkshire', 'wiltshire', 'worcestershire'
    ],
    "scotland": [
        'aberdeenshire', 'angus', 'argyll', 'ayrshire', 'banffshire', 'berwickshire', 'caithness', 'clackmannanshire', 'dumfriesshire',
        'dunbartonshire', 'east lothian', 'fife', 'glasgow', 'inverness-shire', 'isle of arran', 'isle of barra', 'barra', 'isle of benbecula',
        'benbecula', 'isle of bute', 'bute', 'isle of canna', 'canna', 'isle of coll', 'coll', 'isle of colonsay', 'colonsay', 'isle of cumbrae',
        'great cumbrae', 'cumbrae', 'isle of eigg', 'eigg', 'isle of gigha', 'gigha', 'giogha', 'isle of harris', 'harris', 'isle of iona', 'iona',
        'isle of islay', 'islay', 'isle of jura', 'jura', 'isle of lewis', 'lewis', 'isle of mull', 'mull', 'isle of north uist', 'north uist',
        'isle of rum', 'isle of scalpay', 'scalpay', 'isle of skye', 'isle of south uist', 'south uist', 'isle of tiree', 'kincardineshire',
        'kinross-shire', 'kirkcudbrightshire', 'lanarkshire', 'midlothian', 'morayshire', 'nairnshire', 'orkney', 'orkney isles', 'peeblesshire',
        'perthshire', 'renfrewshire', 'ross-shire', 'roxburghshire', 'selkirkshire', 'shetland islands', 'shetland', 'stirlingshire', 'sutherland',
        'west lothian', 'wigtownshire'
    ],
    "wales": [
        'caerphilly', 'cardiff', 'carmarthenshire', 'clwyd', 'dyfed', 'gwent', 'gwynedd', 'mid glamorgan', 'newport', 'pembrokeshire', 'powys',
        'south glamorgan', 'west glamorgan'
    ],
    "northern ireland": [
        'county antrim', 'antrim', 'county armagh', 'armagh', 'county down', 'county fermanagh', 'fermanagh', 'county londonderry', 'londonderry',
        'county tyrone', 'tyrone'
    ]
}


def clean_name(name):
    name = '{}'.format(name.replace('-', ' ').lower().strip())
    name = unidecode(name)

    return name


def normalize_country_code(country):
    country_code = None
    country = country.lower().strip() if country else ''

    if country in ['uk', 'gb', 'united kingdom']:
        country_code = 'uk'

    elif country in ['es', 'spain']:
        country_code = 'es'

    elif country in ['au', 'australia']:
        country_code = 'au'

    elif country in ['nl', 'netherlands']:
        country_code = 'nl'

    elif country in ['cl', 'chile']:
        country_code = 'cl'

    elif country in ['ua', 'ukraine']:
        country_code = 'ua'

    elif country in ['nz', 'new zealand']:
        country_code = 'nz'

    elif country in ['us', 'united states']:
        country_code = 'us'

    elif country in ['ca', 'canada']:
        country_code = 'ca'

    elif country in ['ru', 'russia']:
        country_code = 'ru'

    elif country in ['id', 'indonesia']:
        country_code = 'id'

    elif country in ['th', 'thailand']:
        country_code = 'th'

    elif country in ['pl', 'poland']:
        country_code = 'pl'

    elif country in ['fr', 'france']:
        country_code = 'fr'

    elif country in ['it', 'italy']:
        country_code = 'it'

    elif country in ['tr', 'turkey']:
        country_code = 'tr'

    elif country in ['br', 'brazil']:
        country_code = 'br'

    elif country in ['kr', 'korea', 'south korea']:
        country_code = 'br'

    elif country in ['sa', 'saudi arabia']:
        country_code = 'sa'

    return country_code


def load_uk_provincess():
    global uk_provinces

    if uk_provinces:
        return uk_provinces

    uk_provinces = {}
    data_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'uk_provinces.csv')
    lines = open(data_file).readlines()
    for l in lines:
        parts = [j.strip() for j in l.split(',')]
        if len(parts) == 2:
            city = parts[0].lower()
            province = parts[1]
            if city not in uk_provinces and province.lower() in ALIEXPRESS_UK_PROVINCES:
                uk_provinces[city] = province

    return uk_provinces


def load_aliexpress_countries():
    global aliexpress_countries

    if aliexpress_countries:
        return aliexpress_countries

    data_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'shipping', 'aliexpress_countries.json')
    aliexpress_countries = json.loads(open(data_file).read())

    return aliexpress_countries


def load_ebay_countries():
    global ebay_countries

    if ebay_countries:
        return ebay_countries

    data_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'shipping', 'ebay_countries.json')
    ebay_countries = json.loads(open(data_file).read().lower())

    return ebay_countries


def get_uk_province(city, default=''):
    provinces = load_uk_provincess()
    city = city.lower().strip().split(',')[0].strip()

    province = default
    found = provinces.get(city, default)
    for country, cites in list(ALIEXPRESS_UK_COUNTRIES.items()):
        if (found and found.lower() in cites) or city.lower() in cites:
            province = country
            break

    valide, correction = valide_aliexpress_province('UK', province, city, auto_correct=True)
    if not province or not valide:
        province = 'Other'
    elif correction:
        province = correction.get('province', province)

    return province


def get_fr_city_info(city, zip_code=None, orig_city=None):
    params = {
        'fields': 'nom,code,codesPostaux,codeDepartement,departement,codeRegion,region,population',
    }

    if city and city not in ['ville', 'villers', 'eu']:
        params['nom'] = city

        res = requests.get(url='https://geo.api.gouv.fr/communes', params=params)
        res.raise_for_status()

        res = res.json()
        if len(res) == 1 and res[0].get('_score', 0) >= 0.8:
            # Good City match
            return res.pop()

        for i in res:
            # Find by Zip Code (ex: Courtomer city)
            if zip_code and zip_code in i['codesPostaux']:
                return i

    if zip_code:
        params['codePostal'] = zip_code

        if 'nom' in params:
            del params['nom']

        res = requests.get(url='https://geo.api.gouv.fr/communes', params=params)
        res.raise_for_status()

        zip_code_matchs = []
        for i in res.json():
            if zip_code and zip_code in i['codesPostaux']:
                zip_code_matchs.append(i)

        if len(zip_code_matchs) == 1:
            # Some zip code have more than one city, return only when one match is found
            return zip_code_matchs.pop()
        elif len(set([m['codeRegion'] for m in zip_code_matchs])) == 1:
            match = zip_code_matchs.pop()
            match['nom'] = orig_city or city
            return match
        else:
            raven_client.captureMessage('[FR Address] Too many Zip Matchs',
                                        extra={'zip_code': zip_code, 'city': city, 'match_count': len(zip_code_matchs)})

    raven_client.captureMessage('[FR Address] No Match Found',
                                extra={'zip_code': zip_code, 'city': city})


def fix_fr_address(shipping_address):
    city = clean_name(shipping_address['city'])
    zip_code = shipping_address['zip'].rjust(5, '0')

    cache_key = 'fr_city_{}'.format(hash_list(city, zip_code))
    info = cache.get(cache_key)
    if info is None:
        info = get_fr_city_info(city, zip_code, orig_city=shipping_address['city'])

    if info:
        shipping_address['province'] = info['region']['nom']
        shipping_address['city'] = info['departement']['nom']

        if clean_name(info['nom']) != clean_name(info['departement']['nom']):
            # Add City to address2 field
            if not shipping_address['address2'].strip():
                shipping_address['address2'] = info['nom']
            else:
                shipping_address['address2'] = '{}, {}'.format(shipping_address['address2'].strip(), info['nom'])

        for i in ['province', 'city', 'address2']:
            if type(shipping_address[i]) is str:
                shipping_address[i] = unidecode(shipping_address[i])

        info['city'] = city
        info['zip_code'] = zip_code

        cache.set(cache_key, info, timeout=86400)

    return shipping_address


def fix_br_address(customer_address):
    if customer_address.get('zip'):
        zip_code = customer_address['zip']
        if '-' not in zip_code:
            zip_code = re.sub(r'^(\d{5}).*?(\d{3})$', r'\1-\2', zip_code)
            zip_code = zip_code.strip().rjust(5, '0')
            customer_address['zip'] = zip_code

    return customer_address


def fuzzy_find_in_list(options, value, default=None):
    if options and value:
        f = FuzzySet(options)
        res = f.get(value)
        if res and len(res):
            score, match = res[0]
            if score > 0.8:
                return match

    return default


def find_in_list(items, value):
    if type(items) is dict:
        for key, val in items.items():
            if key.upper() == value.upper():
                return val

    for i in items:
        if i.upper() == value.upper():
            return i

    return None


def valide_aliexpress_province(country, province, city, auto_correct=False):
    country = country.strip() if country else ''
    province = province.strip() if province else ''
    city = city.strip() if city else ''

    country_code = normalize_country_code(country)
    correction = {}

    if auto_correct and city.startswith('st.'):
        city = re.sub(r'^st\. +', 'saint', city)
        correction['city'] = city

    if country_code:
        aliexpress_countries = load_aliexpress_countries()

        province_list = find_in_list(aliexpress_countries, country_code)
        if province_list:
            province_match = fuzzy_find_in_list(list(province_list.keys()), province, default=province) if auto_correct else province

            if province_match and province_list and province_match != province:
                if auto_correct:
                    correction['province'] = province_match
                else:
                    return False, correction

            city_list = find_in_list(province_list, province_match)
            if type(city_list) is list and not len(city_list):
                # Province have a field for city
                return True, correction

            if auto_correct:
                city_match = fuzzy_find_in_list(city_list, city, default=None)
                if city_match and city and city_match and city_match != city:
                    correction['city'] = city_match
            else:
                city_match = city_list and city in city_list

            return bool(city_match), correction

    return True, correction


def support_other_in_province(country):
    """ Return True if the country have "Other" option in Aliexpress Province Dropdown


    Args:
        country: country code or name
    """

    country_code = normalize_country_code(country)
    if country_code:
        aliexpress_countries = load_aliexpress_countries()

        province_list = find_in_list(aliexpress_countries, country_code)
        if province_list:
            return "Other" in province_list

    return False


def aliexpress_country_code_map(country_code):
    maps = {
        'GB': 'UK',
        'AX': 'ALA',
        'CG': 'CG',
        'CD': 'CG',
        'JE': 'JEY',
        'KV': 'KS',
        'ME': 'MNE',
        'RS': 'SRB',
        'GS': 'SGS',
        'GG': 'GGY',
        'BL': 'BLM'
    }

    return maps.get(country_code, country_code)


def ebay_country_code_map(country_code):
    maps = {
        'UK': 'GB',
    }

    return maps.get(country_code, country_code)


def load_countries():
    global countries_code

    if countries_code is None:
        countries_code = json.load(
            open(os.path.join(settings.BASE_DIR, 'app/data/shipping/countries.json')),
            object_pairs_hook=OrderedDict)

    return countries_code


def get_counrties_list():
    return list(load_countries().items())


def country_from_code(country_code, default=None):
    countries = load_countries()

    if default is not None:
        return countries.get(country_code, default)
    else:
        return countries.get(country_code, country_code)


def province_from_code(country_code, province_code):
    global countries_code

    country_code = country_code.lower()
    if country_code not in provinces_code:
        path = os.path.join(settings.BASE_DIR, 'app/data/shipping/provinces/{}.json'.format(country_code))
        if os.path.isfile(path):
            provinces_code[country_code] = json.load(open(path))

    province = provinces_code.get(country_code, {}).get(province_code)

    return province if province else province_code


def ebay_country_code(country_name):
    return load_ebay_countries().get(country_name.lower())
