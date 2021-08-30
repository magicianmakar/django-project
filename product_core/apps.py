from django.apps import AppConfig


class ProductCoreConfig(AppConfig):
    name = 'product_core'

    def ready(self):
        import product_core.signals # noqa
