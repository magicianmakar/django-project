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
