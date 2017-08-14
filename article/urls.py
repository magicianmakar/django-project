from django.conf.urls import patterns, url

urlpatterns = patterns(
    'article.views',
    url(r'^$', 'index'),
    url(r'^tagged/(?P<tag>[a-z-]+)$$', 'index', name="tagged"),
    url(r'^view/(?P<id_article>\d+)$', 'view'),
    url(r'^view/(?P<slug_article>[a-zA-Z0-9-_]+)$', 'view'),
    url(r'^edit/(?P<article_id>\d+)$', 'edit', name="edit"),
    url(r'^add$', 'submit', name="add-page"),
    url(r'^(?P<id_article>\d+)$', 'view'),
    url(r'^(?P<slug_article>[a-zA-Z0-9-_]+)$', 'view'),
)
