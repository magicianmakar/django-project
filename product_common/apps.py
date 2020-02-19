from django.apps import AppConfig


class ProductCommonConfig(AppConfig):
    name = 'product_common'

    def ready(self):
        from . import signals  # noqa
