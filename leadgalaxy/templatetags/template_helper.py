from django import template
from django.template import Context, Template
import json

register = template.Library()

@register.simple_tag(takes_context = True)
def render_project(context, tpl, project):
    template = Template("{% load template_helper %}\n" + tpl)
    ctx = Context({
        'project': project,
        'template': project.template,
        'metrics': project.get_metrics('all'),
    })

    return template.render(ctx)

@register.simple_tag(takes_context = True)
def render_category(context, tpl, category):
    template = Template("{% load template_helper %}\n" +tpl)
    ctx = Context({
        'project': category.project,
        'template': category.project.template,
        'category': category,
        'metrics': category.project.get_metrics('all'),

    })

    return template.render(ctx)


@register.simple_tag(takes_context = True)
def encode_order(context, data, auto):
    data['auto'] = (auto == 'True')
    return json.dumps(data).encode('base64')

@register.simple_tag(takes_context = True)
def base64_encode(context, data):
    return data.encode('base64')
