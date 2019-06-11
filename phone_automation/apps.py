from django.apps import AppConfig


class TwilioConfig(AppConfig):
    name = 'phone_automation'

    def ready(self):
        from . import receivers  # NOQA
