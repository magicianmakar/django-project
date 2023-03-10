from django import template
from django.http import QueryDict
from django.utils.safestring import mark_safe
from django.urls import reverse

from urllib.parse import urlparse, urlunparse

register = template.Library()


@register.simple_tag(takes_context=True)
def query_replace(context, field, value):
    dict_ = context['request'].GET.copy()
    dict_[field] = value
    return dict_.urlencode()


@register.simple_tag(takes_context=True)
def query_toggle(context, field, values):
    dict_ = context['request'].GET.copy()

    values = values.split(',')
    try:
        index = values.index(dict_[field])
    except:
        index = -1

    index = (index + 1) % len(values)

    dict_[field] = values[index]

    return ('%s=%s' % (field, dict_[field]))


@register.simple_tag(takes_context=True)
def sort_icon(context, field, value):
    dict_ = context['request'].GET.copy()
    order_desc = 'true'
    order_by = 'update'
    if 'desc' in dict_:
        order_desc = dict_['desc']
    if field in dict_:
        order_by = dict_[field]
    if value in order_by:
        if order_desc == 'true':
            return mark_safe('<i class="fa fa-sort-desc"></i>')
        else:
            return mark_safe('<i class="fa fa-sort-asc"></i>')

    return ''


@register.simple_tag(takes_context=True)
def url_toggle(context, field, values):
    url = context['request'].get_full_path()
    (scheme, netloc, path, params, query, fragment) = urlparse(url)
    query_dict = QueryDict(query).copy()

    values = values.split(',')
    try:
        index = values.index(query_dict[field])
    except:
        index = -1

    index = (index + 1) % len(values)

    query_dict[field] = values[index]

    query = query_dict.urlencode()
    return urlunparse((scheme, netloc, path, params, query, fragment))


@register.simple_tag(takes_context=True)
def url_replace(context, field, value):
    url = context['request'].get_full_path()
    (scheme, netloc, path, params, query, fragment) = urlparse(url)
    query_dict = QueryDict(query).copy()
    query_dict[field] = value
    query = query_dict.urlencode()
    return urlunparse((scheme, netloc, path, params, query, fragment))


@register.simple_tag(takes_context=True)
def url_toggle_replace(context, toggle_field, toggle_valuem, replace_field, replace_value):
    (scheme, netloc, path, params, query, fragment) = urlparse(url_toggle(context, toggle_field, toggle_valuem))
    query_dict = QueryDict(query).copy()
    query_dict[replace_field] = replace_value
    query = query_dict.urlencode()
    return urlunparse((scheme, netloc, path, params, query, fragment))


@register.simple_tag(takes_context=True)
def url_multi_replace(context, **kwargs):
    url = context['request'].get_full_path()
    (scheme, netloc, path, params, query, fragment) = urlparse(url)
    query_dict = QueryDict(query).copy()

    for k, v in kwargs.items():
        query_dict[k] = v

    query = query_dict.urlencode()
    return urlunparse((scheme, netloc, path, params, query, fragment))


@register.simple_tag(takes_context=True)
def url_path(context, new_path):
    ''' Change url path'''
    url = context['request'].get_full_path()
    (scheme, netloc, path, params, query, fragment) = urlparse(url)
    return urlunparse((scheme, netloc, new_path, params, query, fragment))


@register.simple_tag(takes_context=True)
def page_full_url(context):
    url = context['request'].build_absolute_uri()
    return url


@register.simple_tag(takes_context=True)
def query_active(context, field, value, selector, islist=False):
    dict_ = context['request'].GET.copy()

    if islist and value in dict_.getlist(field):
        return selector
    elif dict_.get(field) == value:
        return selector
    else:
        return ''


@register.simple_tag(takes_context=True)
def build_absolute_uri(context, path, reverse_url=False, **kwargs):
    if reverse_url:
        return context['request'].build_absolute_uri(reverse(path, kwargs=kwargs))
    else:
        return context['request'].build_absolute_uri(path)
