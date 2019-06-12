from django.apps import AppConfig


class WooCommerceConfig(AppConfig):
    name = 'woocommerce_core'
    verbose_name = "WooCommerce"

    def ready(self):
        import woocommerce_core.signals # noqa
