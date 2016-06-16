import os
import simplejson as json
from django.conf import settings


def load_uk_provincess():
    data_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'uk_provinces.csv')
    uk_provinces = {}
    lines = open(data_file).readlines()
    for l in lines:
        l = l.split('|')
        if len(l) == 2:
            uk_provinces[l[0]] = l[1].strip()

    return uk_provinces
