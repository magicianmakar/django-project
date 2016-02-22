from django import template
from urlparse import urlparse, urlunparse
from django.http import QueryDict

register = template.Library()

@register.filter(name='can')
def can(user, perm_name):
    """
    Usage in template:
    {% if request.user|can:'image_uploader.view' %}
    {% endif %}
    """

    return user.is_authenticated() and user.profile.can(perm_name)

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
