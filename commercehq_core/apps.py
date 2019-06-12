from django.apps import AppConfig


class CommerceHQConfig(AppConfig):
    name = 'commercehq_core'
    verbose_name = "CommerceHQ"

    def ready(self):
        import commercehq_core.signals # noqa
