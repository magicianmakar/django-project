from django.apps import AppConfig


class PrintsConfig(AppConfig):
    name = 'prints'
    verbose_name = 'Print On Demand'

    def ready(self):
        import prints.signals # noqa
