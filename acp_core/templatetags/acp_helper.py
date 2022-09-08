from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def shopify_charge_class(charge):
    status = charge.get('status')
    if status == 'active':
        cls = 'color-ok'
    elif status == 'expired':
        cls = 'color-warning'
    else:
        cls = 'color-danger'

    return mark_safe(f' class="{cls}" ')


@register.simple_tag
def shopify_sub_class(charge):
    return shopify_charge_class(charge)


@register.simple_tag
def stripe_charge_class(charge):
    status = charge.get('status')
    cls = None
    if status == 'active' and not charge.dispute:
        if charge.amount_refunded:
            cls = 'color-warning'
        else:
            cls = 'color-ok'

    elif status == 'succeeded':
        cls = 'color-ok'
    elif status == 'failed':
        cls = 'color-danger'

    return mark_safe(f' class="{cls}" ')


@register.filter
def as_percentage_of(part, whole):
    try:
        return "%d%%" % (float(part) / whole * 100) if whole > 0 else '0%'
    except (ValueError, ZeroDivisionError):
        return ""
