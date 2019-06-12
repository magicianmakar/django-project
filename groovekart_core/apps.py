from django.apps import AppConfig


class GroovekartCoreConfig(AppConfig):
    name = 'groovekart_core'
    verbose_name = "GrooveKart"

    def ready(self):
        import groovekart_core.signals # noqa
