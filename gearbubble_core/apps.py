from django.apps import AppConfig


class GearBubbleConfig(AppConfig):
    name = 'gearbubble_core'
    verbose_name = "GearBubble"

    def ready(self):
        import gearbubble_core.signals # noqa
