from django.apps import AppConfig


class LastSeenConfig(AppConfig):
    name = 'last_seen'
    verbose_name = "Last Seen"

    def ready(self):
        import last_seen.signals # noqa
