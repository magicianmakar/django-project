"""
Implementation of the jquery.param function
Used due to urllib.parse.urlencode not working properly with SureDone API
https://github.com/jquery/jquery/blob/main/src/serialize.js
"""
import re
from urllib.parse import quote

rbracket = re.compile(r'\[]$')


def add(k, v, s):
    s.append(quote(k) + '=' + quote(str(v) if v is not None else ''))


def build_params(prefix, obj, s):
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            # Serialize list item
            if rbracket.search(prefix):
                # Treat each array item as a scalar.
                add(prefix, v, s)
            else:
                # Item is non-scalar (array or object), encode its numeric index.
                index = (str(i) if (isinstance(v, dict) or isinstance(v, list)) and v is not None else '')
                build_params(prefix + '[' + index + ']', v, s)
    elif isinstance(obj, dict):
        # Serialize object item.
        for name in obj.keys():
            build_params(prefix + '[' + name + ']', obj[name], s)
    else:
        # Serialize scalar item.
        add(prefix, obj, s)


def param(a):
    s = []

    if a is None:
        return ''

    for prefix in a.keys():
        build_params(prefix, a[prefix], s)

    return '&'.join(s)
