from models import Comment
from django import forms
from django.contrib.auth.models import User

class ArticleForm(forms.Form):
    title = forms.CharField()
    body = forms.CharField(widget=forms.Textarea)
    tags = forms.CharField(required=False)

class AnonymouseArticleForm(ArticleForm):
    name = forms.CharField(max_length=140)
    email = forms.EmailField(max_length=254)

class CommentForm(forms.Form):
    title = forms.CharField(max_length=140)
    body = forms.CharField(widget=forms.Textarea)
    parent = forms.CharField(initial=0)

