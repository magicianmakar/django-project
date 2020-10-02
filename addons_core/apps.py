from django.apps import AppConfig


class AddonsCoreConfig(AppConfig):
    name = 'addons_core'
    verbose_name = 'Addons'

    def ready(self):
        import addons_core.signals  # noqa
