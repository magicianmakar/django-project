from django import template

register = template.Library()


@register.filter
def trial_days_left(addon, user):
    user_addon = user.profile.addons_mapping.get(addon.id)
    return user_addon.trial_days_left if user_addon else addon.trial_period_days
