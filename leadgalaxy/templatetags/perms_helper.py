from django import template

register = template.Library()


@register.filter(name='can')
def can(user, perm_name):
    """
    Usage in template:
    {% if request.user|can:'image_uploader.view' %}
    {% endif %}
    """

    if user.is_authenticated:
        if 'leadgalaxy.' in perm_name:
            return user.has_perm(perm_name)
        else:
            return user.can(perm_name)

    return False


@register.filter
def plan_have_feature(plan, perm_name):
    return plan.permissions.filter(name__iexact=perm_name).exists()


@register.filter
def can_view_sidebar_item(user, item):
    return (user.profile.plan.register_hash in item.plans()) or (
        item.inherit_plan and user.is_subuser and can_view_sidebar_item(user.profile.subuser_parent, item))


@register.filter(name='has_group')
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


@register.filter
def supplier_type(s):
    if not s:
        return s

    if s == 'aliexpress':
        return 'Aliexpress'
    elif s == 'ebay':
        return 'eBay'
    else:
        return s.title()
