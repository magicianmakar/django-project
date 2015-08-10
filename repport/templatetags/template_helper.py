from django import template
from django.template import Context, Template

register = template.Library()

@register.simple_tag(takes_context = True)
def render_project(context, tpl, project):
    template = Template("{% load template_helper %}\n" + tpl)
    ctx = Context({
        'project': project,
        'template': project.template,
    })

    return template.render(ctx)

@register.simple_tag(takes_context = True)
def render_category(context, tpl, category):
    template = Template("{% load template_helper %}\n" +tpl)
    ctx = Context({
        'project': category.project,
        'template': category.project.template,
        'category': category,
    })

    return template.render(ctx)

