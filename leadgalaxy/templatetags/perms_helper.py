from django import template
from urlparse import urlparse, urlunparse
from django.http import QueryDict
from leadgalaxy.models import LEAD_GROUPS

register = template.Library()

# @register.simple_tag(takes_context = True)
# def in_group(context, group):
#     user = context['user']
    # return LEAD_GROUPS[group_name] in user.groups.all().values_list('id', flat=True)

@register.filter(name='in_group')
def in_group(user, group_name):
    """
    Usage in template:
    {% if request.user|in_group:'galaxy_admin' %}
        In galaxy_admin Group
    {% endif %}
    """
    return LEAD_GROUPS[group_name] in user.groups.all().values_list('id', flat=True)

@register.filter(name='in_groups')
def in_groups(user, groups_name):
    """
    Usage in template:
    {% if request.user|in_groups:'galaxy_admin,galaxy_market' %}
        In galaxy_admin or galaxy_market Group
    {% endif %}
    """

    for i in groups_name.split(','):
        if in_group(user, i):
            return True

    return False
