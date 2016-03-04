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


@register.simple_tag(takes_context=True)
def sort_icon(context, field, value):
    dict_ = context['request'].GET.copy()
    if field in dict_:
        if value in dict_[field]:
            if dict_[field][0] == '-':
                return '<i class="fa fa-sort-desc"></i>'
            else:
                return '<i class="fa fa-sort-asc"></i>'

    return ''

@register.simple_tag(takes_context = True)
def url_toggle(context, field, values):
    url = context['request'].get_full_path()
    (scheme, netloc, path, params, query, fragment) = urlparse(url)
    query_dict = QueryDict(query).copy()

    values = values.split(',')
    try:
        index = values.index(query_dict[field])
    except:
        index = -1

    index = (index+1)%len(values)

    query_dict[field] = values[index]

    query = query_dict.urlencode()
    return urlunparse((scheme, netloc, path, params, query, fragment))

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
def query_active(context, field, value, selector):
    dict_ = context['request'].GET.copy()

    if dict_.get(field) == value:
        return selector
    else:
        return ''


