from django.apps import AppConfig


class StripeSubscriptionConfig(AppConfig):
    name = 'stripe_subscription'
    verbose_name = "Stripe Subscriptions"

    def ready(self):
        import stripe_subscription.signals # noqa
