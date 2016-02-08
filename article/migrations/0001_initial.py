# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Article',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=140)),
                ('slug', models.CharField(max_length=140, blank=True)),
                ('body', models.TextField()),
                ('stat', models.IntegerField(default=2, verbose_name=b'Publish stat', choices=[(0, b'Published'), (1, b'Draft'), (2, b'Waitting review')])),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('author', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=140)),
                ('body', models.TextField()),
                ('votes', models.IntegerField(default=0)),
                ('stat', models.IntegerField(default=2, verbose_name=b'Publish stat', choices=[(0, b'Published'), (1, b'Draft'), (2, b'Waitting review')])),
                ('parent', models.IntegerField(default=0, verbose_name=b'Parent comment')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('article', models.ForeignKey(to='article.Article')),
                ('author', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='CommentVote',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Vote date')),
                ('vote_value', models.IntegerField(verbose_name=b'Vore Value')),
                ('article', models.ForeignKey(to='article.Article')),
                ('comment', models.ForeignKey(to='article.Comment')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
