from django import template

register = template.Library()


@register.filter(name='can')
def can(user, perm_name):
    """
    Usage in template:
    {% if request.user|can:'image_uploader.view' %}
    {% endif %}
    """

    if user.is_authenticated():
        if 'leadgalaxy.' in perm_name:
            return user.has_perm(perm_name)
        else:
            return user.can(perm_name)

    return False

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
