from django import forms

from .models import PUBLISH_STAT, ARTICLE_FORMAT


class ArticleForm(forms.Form):
    title = forms.CharField()
    body = forms.CharField(widget=forms.Textarea, required=False)
    tags = forms.CharField(required=False)
    stat = forms.ChoiceField(choices=PUBLISH_STAT[:2])

    show_header = forms.BooleanField(required=False)
    show_sidebar = forms.BooleanField(required=False)
    show_searchbar = forms.BooleanField(required=False)
    show_breadcrumb = forms.BooleanField(required=False)

    candu_slug = forms.CharField(required=False)
    style = forms.CharField(widget=forms.Textarea, required=False)
    body_format = forms.ChoiceField(choices=ARTICLE_FORMAT, required=False)


class AnonymouseArticleForm(ArticleForm):
    name = forms.CharField(max_length=140)
    email = forms.EmailField(max_length=254)


class CommentForm(forms.Form):
    title = forms.CharField(max_length=140)
    body = forms.CharField(widget=forms.Textarea)
    parent = forms.CharField(initial=0)
