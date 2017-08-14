from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.exceptions import PermissionDenied

from article.models import *
from article.forms import ArticleForm

import simplejson as json


def index(request, tag=None):
    if tag:
        tags = ArticleTag.objects.filter(Q(title__iexact=tag) | Q(title__iexact=tag.replace('-', ' ')))
        articles = Article.objects.filter(Q(tags__in=tags)).order_by('-created_at')
    else:
        if not request.user.is_superuser:
            raise PermissionDenied()

        articles = Article.objects.order_by('-created_at')

    if not request.user.is_superuser:
        articles = articles.filter(stat=0)

    return render(request, 'article/index.html', {
        'articles': articles,
        'tag': tag,
        'page': 'acp_pages',
        'breadcrumbs': ['Pages']

    })


def view(request, id_article=None, slug_article=None):
    try:
        article = Article.objects.get(pk=id_article)
    except Article.DoesNotExist:
        article = get_object_or_404(Article, slug=slug_article)

    if article.stat != 0 and not request.user.is_superuser:
        raise Http404('Not published')

    if not request.user.is_superuser:
        # Update this way so we don't change updated_at
        Article.objects.filter(id=article.id).update(views=article.views + 1)

    return render(request, 'article/view.html', {
        'article': article,
    })


@login_required
def submit(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    if request.method == 'POST':
        form = ArticleForm(request.POST)

        article = _save_submittion(request, form)
        if(article):
            messages.success(request, 'Page successful saved.')
            return redirect('article.views.view', slug_article=article.slug)
        else:
            messages.error(request, 'Unknown error')
    else:
        form = ArticleForm()

    tags = []
    for i in ArticleTag.objects.all():
        tags.append(i.title)

    return render(request, 'article/submit.html', {
        'tags': json.dumps(tags),
        'form': form,
    })


@login_required
def edit(request, article_id):
    if not request.user.is_superuser:
        raise PermissionDenied()

    article = Article.objects.get(pk=article_id)

    if(request.method == 'POST'):
        form = ArticleForm(request.POST)

        article = _save_submittion(request, form, article)
        if(article):
            messages.success(request, 'Page successful saved.')
            return redirect('article.views.view', slug_article=article.slug)
        else:
            messages.error(request, 'Unknown error')
    else:
        form = ArticleForm(initial={
            'title': article.title,
            'body': article.body,
            'tags': ','.join(article.tags.all().values_list('title', flat=1))})

    tags = []
    for i in ArticleTag.objects.all():
        tags.append(i.title)

    return render(request, 'article/submit.html', {
        'article': article,
        'tags': json.dumps(tags),
        'form': form,
    })


@login_required
def _save_submittion(request, form, article=None):
    if(form.is_valid()):
        article_title = form.cleaned_data['title']
        article_text = form.cleaned_data['body']
        tags = form.cleaned_data['tags']
        stat = form.cleaned_data['stat']

        if not article:
            article = Article(title=article_title, body=article_text, author=request.user, stat=stat)
        else:
            article.title = article_title
            article.body = article_text
            article.stat = stat

            article.tags.clear()

        article.save()

        if tags.strip():
            for i in tags.split(','):
                try:
                    i = i.strip()
                    if not i:
                        continue

                    tag = ArticleTag.objects.get(title=i)
                except:
                    tag = ArticleTag(title=i)
                    tag.save()

                article.tags.add(tag)

        article.save()

        return article
    else:
        return False


def json_response(data):
    return HttpResponse(json.dumps(data, sort_keys=True, indent=2),
                        content_type='application/json; charset=UTF-8')
