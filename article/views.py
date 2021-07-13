import simplejson as json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from article.forms import ArticleForm
from article.models import Article, ArticleTag
from leadgalaxy.models import AdminEvent


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

    if article.stat != 0 and not request.user.is_staff:
        raise Http404('Not published')

    if not request.user.is_staff:
        # Update this way so we don't change updated_at
        Article.objects.filter(id=article.id).update(views=article.views + 1)

    if request.user.is_staff:
        breadcrumbs = [{'title': 'Pages', 'url': reverse(index)}, article.title]
    else:
        breadcrumbs = [article.title]

    return render(request, 'article/view.html', {
        'article': article,
        'breadcrumbs': breadcrumbs,
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
        if request.user.is_staff:
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
    if not request.user.is_staff:
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
    if not request.user.is_staff:
        raise PermissionDenied()

    article = Article.objects.get(pk=article_id)

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
            'body_format': article.body_format,
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

        if not article:
            event_name = 'add'
            article = Article(author=request.user)
        else:
            event_name = 'edit'

        article.title = form.cleaned_data['title']

        article.body = form.cleaned_data['body']
        article.stat = form.cleaned_data['stat']

        article.show_header = form.cleaned_data['show_header']
        article.show_sidebar = form.cleaned_data['show_sidebar']
        article.show_searchbar = form.cleaned_data['show_searchbar']
        article.show_breadcrumb = form.cleaned_data['show_breadcrumb']

        article.candu_slug = form.cleaned_data['candu_slug']
        article.style = form.cleaned_data['style']
        article.body_format = form.cleaned_data['body_format']

        article.save()

        tags = form.cleaned_data['tags']
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

        AdminEvent.objects.create(
            user=request.user,
            event_type=f'{event_name}_article',
            target_user=None,
            data=json.dumps({'article': article.id}))

        return article
    else:
        return False
