import os
import simplejson as json
from hashlib import md5
from collections import OrderedDict

from django.core.cache import cache
from django.conf import settings


uk_provinces = None
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
    ],
    "anguilla": [],
    "bermuda": [],
    "british indian ocean territory": [],
    "british virgin islands": [],
    "cayman islands": [],
    "falkland islands": [],
    "gibraltar": [],
    "guernsey": [],
    "isle of man": [],
    "jersey": [],
    "montserrat": [],
    "pitcairn islands": [],
    "south georgia & south sandwich islands": [],
    "st helena, ascension, tristan da cunha": [],
    "turks and caicos islands": [],
}

ALIEXPRESS_ES_PROVINCES = [
    "a coruna", "alacant", "alava", "albacete", "almeria", "asturias", "avila", "badajoz", "balearic islands", "barcelona", "burgos", "caceres",
    "cadiz", "canary islands", "cantabria", "castello", "ciudad real", "cordoba", "cuenca", "girona", "granada", "guadalajara", "guipuzcoa", "huelva",
    "huesca", "jaen", "la rioja", "las palmas", "leon", "lleida", "lugo", "madrid", "malaga", "murcia", "navarra", "ourense", "palencia",
    "pontevedra", "salamanca", "santa cruz de tenerife", "segovia", "sevilla", "soria", "tarragona", "teruel", "toledo", "valencia", "valladolid",
    "vizcaya", "zamora", "zaragoza"
]

ALIEXPRESS_AU_PROVINCES = [
    "Australian Capital Territory", "Jervis Bay Territory", "New South Wales", "Northern Territory", "Queensland", "South Australia",
    "Tasmania", "Victoria", "Western Australia"
]


def load_uk_provincess():
    global uk_provinces

    if uk_provinces:
        return uk_provinces

    uk_provinces = {}
    data_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'uk_provinces.csv')
    lines = open(data_file).readlines()
    for l in lines:
        l = [j.strip() for j in l.split(',')]
        if len(l) == 2:
            city = l[0].lower()
            province = l[1]
            if city not in uk_provinces and province.lower() in ALIEXPRESS_UK_PROVINCES:
                uk_provinces[city] = province

    return uk_provinces


def get_uk_province(city, default=''):
    provinces = load_uk_provincess()
    city = city.lower().strip().split(',')[0].strip()

    found = provinces.get(city, default)
    for country, cites in ALIEXPRESS_UK_COUNTRIES.items():
        if (found and found.lower() in cites) or city.lower() in cites:
            return country

    return default


def valide_aliexpress_province(country, province):
    if not province:
        province = ''

    country = country.lower()
    province = province.lower().strip()

    if country in ['uk', 'gb', 'united kingdom']:
        return (province in ALIEXPRESS_UK_PROVINCES or province in ALIEXPRESS_UK_COUNTRIES.keys())
    elif country in ['es', 'spain']:
        return province in ALIEXPRESS_ES_PROVINCES
    elif country in ['au', 'australia']:
        return province in ALIEXPRESS_AU_PROVINCES

    return True


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
