# -*- coding:utf8 -*-

from django.db import models
from django.contrib.auth.models import User
from django.template.defaultfilters import slugify
from multiselectfield import MultiSelectField

PUBLISH_STAT = (
    (0, 'Published'),
    (1, 'Draft'),
    (2, 'Waitting review'),
)

PLAN_CHOICES = (('64543a8eb189bae7f9abc580cfc00f76', 'Vip Elite'),
              ('3eccff4f178db4b85ff7245373102aec', 'Elite'),
              ('b17d8eacbb02bb907c2ccc854f7c282d', 'Team Shopify'),
              ('55cb8a0ddbc9dacab8d99ac7ecaae00b', 'Pro'),
              ('2877056b74f4683ee0cf9724b128e27b', 'Basic'),
              ('606bd8eb8cb148c28c4c022a43f0432d', 'Free'))


class Article(models.Model):
    class Meta:
        verbose_name = "Page"
        verbose_name_plural = "Pages"

    title = models.CharField(max_length=140)
    slug = models.CharField(max_length=140)
    body = models.TextField()
    author = models.ForeignKey(User)
    stat = models.IntegerField(choices=PUBLISH_STAT, default=0, verbose_name='Publish stat')
    tags = models.ManyToManyField('ArticleTag', blank=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.title

    def comments_count(self):
        return Comment.objects.filter(article=self).count()

    def save(self, **kwargs):
        if not self.slug:
            slug = slugify(self.title)
            while True:
                try:
                    article = Article.objects.get(slug=slug)
                    if article == self:
                        self.slug = slug
                        break
                    else:
                        slug = slug + '-'
                except:
                    self.slug = slug
                    break

        super(Article, self).save()

class ArticleTag(models.Model):
    class Meta:
        verbose_name = "Page Tag"
        verbose_name_plural = "Page Tags"

    title = models.CharField(unique=True, max_length=50)
    index = models.IntegerField(default=0)

    def formated(self):
        return self.title.replace('-', ' ').replace('_', ' ').title()

    def get_link(self):
        return '/pages/tagged/{}'.format(self.title.replace(' ', '-').lower())

    def __str__(self):
        return self.title

class SidebarLink(models.Model):
    class Meta:
        verbose_name = "Sidebar Link"
        verbose_name_plural = "Sidebar Links"
        ordering = ['-order', 'title']

    title = models.CharField(max_length=100)
    link = models.CharField(max_length=512)
    badge = models.CharField(blank=True, default='', max_length=20)
    order = models.IntegerField(default=0)
    new_tab = models.BooleanField(default=False)
    icon = models.CharField(blank=True, default='', max_length=20)

    parent = models.ForeignKey('SidebarLink', on_delete=models.SET_NULL, related_name='childs', blank=True, null=True)
    plans = MultiSelectField(choices=PLAN_CHOICES)

    def __str__(self):
        return self.title

class Comment(models.Model):
    title = models.CharField(max_length=140)
    body = models.TextField()
    votes = models.IntegerField(default=0)
    stat = models.IntegerField(choices=PUBLISH_STAT, 
                                default=0,
                                verbose_name='Publish stat')

    parent = models.IntegerField(default=0, verbose_name='Parent comment')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')  

    author = models.ForeignKey(User)
    article = models.ForeignKey(Article)

    def __unicode__(self):
        return self.title

class CommentVote(models.Model):
    article = models.ForeignKey(Article)
    comment = models.ForeignKey(Comment)
    user = models.ForeignKey(User)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Vote date')
    vote_value = models.IntegerField(verbose_name='Vore Value')

    def __unicode__(self):
        return "%s: %s" %(('Up' if self.vote_value>0 else 'Down'), self.article.title)
