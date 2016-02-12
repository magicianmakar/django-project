from django import template
from django.template import Context, Template
import json
from urlparse import urlparse

register = template.Library()


@register.simple_tag(takes_context=True)
def render_project(context, tpl, project):
    template = Template("{% load template_helper %}\n" + tpl)
    ctx = Context({
        'project': project,
        'template': project.template,
        'metrics': project.get_metrics('all'),
    })

    return template.render(ctx)


@register.simple_tag(takes_context=True)
def render_category(context, tpl, category):
    template = Template("{% load template_helper %}\n" + tpl)
    ctx = Context({
        'project': category.project,
        'template': category.project.template,
        'category': category,
        'metrics': category.project.get_metrics('all'),

    })

    return template.render(ctx)


@register.simple_tag(takes_context=True)
def encode_order(context, data, auto):
    data['auto'] = (auto == 'True')
    return json.dumps(data).encode('base64').replace('\n', '')


@register.simple_tag(takes_context=True)
def base64_encode(context, data):
    return data.encode('utf8').encode('base64').replace('\n', '')


@register.simple_tag(takes_context=True)
def json_dumps(context, data):
    return json.dumps(data)


@register.simple_tag(takes_context=True)
def remove_link_query(context, link):
    if not link:
        return ''

    parsed = urlparse(link)
    return parsed.scheme + "://" + parsed.netloc + parsed.path
