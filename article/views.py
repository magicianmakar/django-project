from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.core.exceptions import PermissionDenied

from article.models import *
from article.forms import ArticleForm, CommentForm

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
        Article.objects.filter(id=article.id).update(views=article.views+1)

    comments = Comment.objects.filter(article=article)

    return render(request, 'article/view.html', {
        'article': article,
        'comments': _sort_comments(comments),
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
def comment_vote(request, action, article_id, comment_id):
    try:
        value = (1 if action.lower() == 'up' else -1)

        article = Article.objects.get(pk=article_id)
        comment = Comment.objects.get(pk=comment_id)

        try:
            vote = CommentVote.objects.get(user=request.user,
                                           article=article,
                                           comment=comment)
            if(vote.vote_value != value):
                vote.vote_value = value
        except:
            vote = CommentVote(user=request.user,
                               article=article,
                               comment=comment,
                               vote_value=value)

        vote.save()

        total_vote_value = 0
        for v in CommentVote.objects.filter(article=article, comment=comment):
            total_vote_value = total_vote_value + v.vote_value

        comment.votes = total_vote_value
        comment.save()

        return json_response({'new_count': total_vote_value})

    except Exception as e:
        return json_response({'error': unicode(e)})
        pass


@login_required
@require_POST
def comment_add(request, article_id):

    # comment_title = request.POST.get('title')
    # comment_body = xss_clean(request.POST.get('body'))
    # comment_parent = int(request.POST.get('parent'))

    form = CommentForm(request.POST)
    if(form.is_valid()):
        comment = Comment(title=form.cleaned_data['title'],
                          body=xss_clean(form.cleaned_data['body']),
                          parent=form.cleaned_data['parent'],
                          author=request.user,
                          article=Article.objects.get(pk=article_id))
        comment.save()

        messages.success(request, 'Thank you, your comment will be published after review')
        return json_response({'status': 'ok'})
    else:
        return json_response({'status': 'error',
                              'message': dict(form.errors.items())})


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


def _sort_comments(comments):
    index = 0
    parent_map = {}
    for c in comments:
        parent_map[c.pk] = index
        comments[index].childs = []
        index = index + 1

    index = 0
    for c in comments:
        if(c.parent != 0):
            parent_index = parent_map[c.parent]
            comments[parent_index].childs.append(comments[index])
        index = index + 1

    new_comments = []
    for c in comments:
        if(c.parent == 0):
            new_comments.append(c)

    return new_comments


def json_response(data):
    return HttpResponse(json.dumps(data, sort_keys=True, indent=2),
                        content_type='application/json; charset=UTF-8')
