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


@register.simple_tag(takes_context=True)
def price_diff(context, from_, to_, reverse_colors=False):
    if from_ is not float:
        from_ = float(from_)

    if to_ is not float:
        to_ = float(to_)

    colors = ['red', 'green'] if reverse_colors else ['green', 'red']

    if from_ > to_:
        if from_ > 0:
            return '<span style="color:%s"><i class="fa fa-sort-desc"></i> %0.0f%%</span>' % (colors[0], (((to_ - from_) * 100.) / from_))
        else:
            return '<span style="color:%s"><i class="fa fa-sort-desc"></i></span>' % (colors[0])

    else:
        if from_ > 0:
            return '<span style="color:%s"><i class="fa fa-sort-asc"></i> +%0.0f%%</span>' % (colors[1], (((to_ - from_) * 100.) / from_))
        else:
            return '<span style="color:%s"><i class="fa fa-sort-desc"></i></span>' % (colors[0])
