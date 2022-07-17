from django import template
from django.conf import settings
from leadgalaxy.utils import set_url_query

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
    if plan.parent_plan:
        permissions = plan.parent_plan.permissions
    else:
        permissions = plan.permissions
    return permissions.filter(name__iexact=perm_name).exists()


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
        return 'AliExpress'
    elif s == 'ebay':
        return 'eBay'
    elif s == 'pls':
        return 'Dropified'
    else:
        return s.title()


@register.filter
def is_supplement_seen(user_supplement, user):
    user_id = user.id
    seen_users = user_supplement.get_seen_users_list()

    if 'All' in seen_users or user_id in seen_users:
        return True

    return False


@register.filter
def create_walmart_affiliate_link(product_url, user):
    user_id = user.id
    walmart_affiliate_link = settings.WALMART_AFFILIATE_LINK
    walmart_affiliate_link = set_url_query(walmart_affiliate_link, "subId1", user_id)
    walmart_affiliate_link = set_url_query(walmart_affiliate_link, "u", product_url)
    return walmart_affiliate_link


@register.filter(name='supplies')
def supplies(user, item):
    return user.supplies(item)
