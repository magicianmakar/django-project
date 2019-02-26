from django.apps import AppConfig


class ArticleConfig(AppConfig):
    name = 'article'
    verbose_name = "Pages and Links"

    def ready(self):
        import article.signals # noqa
