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

    # Comments
    url(r'^comment/vote/(?P<action>\w+)/(?P<article_id>\d+)/(?P<comment_id>\d+)$', 'comment_vote'),
    url(r'^comment/add/(?P<article_id>\d+)$', 'comment_add'),
)
