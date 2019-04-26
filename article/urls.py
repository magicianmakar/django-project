from django.conf.urls import url

import article.views

urlpatterns = [
    url(r'^$', article.views.index, name='article.views.index'),
    url(r'^content/(?P<slug_article>[a-zA-Z0-9-_]+)$', article.views.content, name="article-content-page"),
    url(r'^tagged/(?P<tag>[a-z-]+)$$', article.views.index, name="tagged"),
    url(r'^view/(?P<id_article>\d+)$', article.views.view, name='article.views.view'),
    url(r'^view/(?P<slug_article>[a-zA-Z0-9-_]+)$', article.views.view, name='article.views.view'),
    url(r'^edit/(?P<article_id>\d+)$', article.views.edit, name="edit"),
    url(r'^add$', article.views.submit, name="add-page"),
    url(r'^(?P<id_article>\d+)$', article.views.view, name='article.views.view'),
    url(r'^(?P<slug_article>[a-zA-Z0-9-_]+)$', article.views.view, name='article.views.view'),
]
