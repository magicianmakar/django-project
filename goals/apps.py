from django.apps import AppConfig


class GoalsConfig(AppConfig):
    name = 'goals'

    def ready(self):
        import goals.signals # noqa
