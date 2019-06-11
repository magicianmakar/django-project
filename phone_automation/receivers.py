from leadgalaxy.signals import main_subscription_canceled, main_subscription_updated


def process_callflex_recurings_delete(sender, **kwargs):
    main_stripe_subscription = sender
    custom_callflex_subscriptions = main_stripe_subscription.user.customstripesubscription_set.filter(
        custom_plan__type='callflex_subscription')
    for custom_callflex_subscription in custom_callflex_subscriptions:
        sub = custom_callflex_subscription.refresh()
        sub.delete(at_period_end=True)


main_subscription_canceled.connect(process_callflex_recurings_delete)


def process_callflex_recurings_update(sender, **kwargs):
    main_stripe_subscription = sender
    sub = kwargs['stripe_sub']
    active_plans = []
    for item in sub['items']['data']:
        active_plans.append(item.id)

    custom_callflex_subscriptions = main_stripe_subscription.user.customstripesubscription_set.filter(
        custom_plan__type='callflex_subscription').exclude(subscription_item_id__in=active_plans)

    for custom_callflex_subscription in custom_callflex_subscriptions:
        custom_callflex_subscription.delete()


main_subscription_updated.connect(process_callflex_recurings_update)
