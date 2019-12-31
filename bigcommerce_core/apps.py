from django.apps import AppConfig


class BigCommerceConfig(AppConfig):
    name = 'bigcommerce_core'
    verbose_name = "BigCommerce"

    def ready(self):
        import bigcommerce_core.signals # noqa
