from django.apps import AppConfig


class LeadGalaxyConfig(AppConfig):
    name = 'leadgalaxy'
    verbose_name = "Dropified"

    def ready(self):
        import leadgalaxy.signals # noqa
