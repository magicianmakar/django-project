import simplejson as json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404

from article.forms import ArticleForm
from article.models import Article, ArticleTag


def index(request, tag=None):
    if tag:
        tags = ArticleTag.objects.filter(Q(title__iexact=tag) | Q(title__iexact=tag.replace('-', ' ')))
        articles = Article.objects.filter(Q(tags__in=tags)).order_by('-created_at')
    else:
        if not request.user.is_staff:
            raise PermissionDenied()

        articles = Article.objects.filter(show_header=True).order_by('-created_at')

    if not request.user.is_staff:
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

    if article.stat != 0 and (not request.user.is_superuser and not request.user.is_staff):
        raise Http404('Not published')

    if not request.user.is_staff:
        # Update this way so we don't change updated_at
        Article.objects.filter(id=article.id).update(views=article.views + 1)

    return render(request, 'article/view.html', {
        'article': article,
    })


def content(request, slug_article=None):
    try:
        if slug_article == 'tools-business-tools':
            if not request.user.is_authenticated or not request.user.can('businesstools_page.use'):
                return redirect('index', permanent=True)
        article = Article.objects.get(slug=slug_article)
    except Article.DoesNotExist:
        article = Article(
            title=slug_article.title().replace('-', ' '),
            slug=slug_article,
            body='<h1 class="text-center">Sorry, no content yet.</h1>',
            author=request.user,
            show_header=False
        )
        if request.user.is_superuser or request.user.is_staff:
            article.save()

    if not request.user.is_staff:
        # Update this way so we don't change updated_at
        Article.objects.filter(id=article.id).update(views=article.views + 1)

    return render(request, 'article/view.html', {
        'article': article,
        'tools': True if slug_article == 'tools-business-tools' else False,
        'import_store_list': True if slug_article == 'source-import-products' else False,
    })


@login_required
def submit(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    if request.method == 'POST':
        form = ArticleForm(request.POST)

        article = _save_submittion(request, form)
        if article:
            messages.success(request, 'Page successful saved.')
            return redirect('article.views.view', slug_article=article.slug)
        else:
            messages.error(request, 'Unknown error')
    else:
        form = ArticleForm(initial={
            'show_header': True,
            'show_sidebar': True,
            'show_searchbar': True,
            'show_breadcrumb': True,
        })

    tags = []
    for i in ArticleTag.objects.all():
        tags.append(i.title)

    return render(request, 'article/submit.html', {
        'tags': json.dumps(tags),
        'form': form,
    })


@login_required
def edit(request, article_id):
    article = Article.objects.get(pk=article_id)

    if not request.user.is_superuser:
        raise PermissionDenied()

    if request.method == 'POST':
        form = ArticleForm(request.POST)

        article = _save_submittion(request, form, article)
        if article:
            messages.success(request, 'Page successful saved.')
            return redirect('article.views.view', slug_article=article.slug)
        else:
            messages.error(request, 'Unknown error')
    else:
        form = ArticleForm(initial={
            'title': article.title,
            'body': article.body,
            'stat': article.stat,
            'tags': ','.join(article.tags.all().values_list('title', flat=1)),
            'show_header': article.show_header,
            'show_sidebar': article.show_sidebar,
            'show_searchbar': article.show_searchbar,
            'show_breadcrumb': article.show_breadcrumb,
            'candu_slug': article.candu_slug,
            'style': article.style,
        })

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
    if form.is_valid():
        article_title = form.cleaned_data['title']
        article_text = form.cleaned_data['body']
        tags = form.cleaned_data['tags']
        stat = form.cleaned_data['stat']

        if not article:
            article = Article(title=article_title, body=article_text, author=request.user, stat=stat)

        if article.show_header:
            article.title = article_title

        article.body = article_text
        article.stat = stat

        article.show_header = form.cleaned_data['show_header']
        article.show_sidebar = form.cleaned_data['show_sidebar']
        article.show_searchbar = form.cleaned_data['show_searchbar']
        article.show_breadcrumb = form.cleaned_data['show_breadcrumb']

        article.candu_slug = form.cleaned_data['candu_slug']
        article.style = form.cleaned_data['style']

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
