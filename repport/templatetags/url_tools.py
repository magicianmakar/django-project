from django import template
from urlparse import urlparse, urlunparse
from django.http import QueryDict

register = template.Library()

@register.simple_tag(takes_context = True)
def query_replace(context, field, value):
    dict_ = context['request'].GET.copy()
    dict_[field] = value
    return dict_.urlencode()

@register.simple_tag(takes_context = True)
def query_toggle(context, field, values):
    dict_ = context['request'].GET.copy()

    values = values.split(',')
    try:
        index = values.index(dict_[field])
    except:
        index = -1

    index = (index+1)%len(values)

    dict_[field] = values[index]

    return ('%s=%s'%(field, dict_[field]))

@register.simple_tag(takes_context = True)
def url_replace(context, field, value):
    url = context['request'].get_full_path()
    (scheme, netloc, path, params, query, fragment) = urlparse(url)
    query_dict = QueryDict(query).copy()
    query_dict[field] = value
    query = query_dict.urlencode()
    return urlunparse((scheme, netloc, path, params, query, fragment))

@register.simple_tag(takes_context = True)
def page_full_url(context):
    url = context['request'].build_absolute_uri()
    return url

@register.simple_tag(takes_context = True)
def smart_url(context, base, url):
    link = '<a href="%s">%s</a>'%(url, url.replace('//www.', '//').replace(base, ''))
    return link
