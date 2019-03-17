# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.db.models.deletion


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
                ('stat', models.IntegerField(default=2, verbose_name='Publish stat', choices=[(0, 'Published'), (1, 'Draft'), (2, 'Waitting review')])),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('author', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=140)),
                ('body', models.TextField()),
                ('votes', models.IntegerField(default=0)),
                ('stat', models.IntegerField(default=2, verbose_name='Publish stat', choices=[(0, 'Published'), (1, 'Draft'), (2, 'Waitting review')])),
                ('parent', models.IntegerField(default=0, verbose_name='Parent comment')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('article', models.ForeignKey(to='article.Article', on_delete=django.db.models.deletion.CASCADE)),
                ('author', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='CommentVote',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Vote date')),
                ('vote_value', models.IntegerField(verbose_name='Vore Value')),
                ('article', models.ForeignKey(to='article.Article', on_delete=django.db.models.deletion.CASCADE)),
                ('comment', models.ForeignKey(to='article.Comment', on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
