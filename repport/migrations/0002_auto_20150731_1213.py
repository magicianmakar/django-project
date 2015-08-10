# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Categorie',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('content_analysis', models.TextField(null=True, blank=True)),
                ('content_score', models.TextField(null=True, blank=True)),
                ('color', models.CharField(max_length=32, null=True, blank=True)),
                ('algorithm_usage', models.IntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name='Topic',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('score', models.IntegerField(default=0)),
                ('analysis', models.TextField(null=True, blank=True)),
                ('recommendations', models.TextField(null=True, blank=True)),
                ('guidelines', models.TextField(null=True, blank=True)),
                ('action_description', models.TextField(null=True, blank=True)),
                ('categorie', models.ForeignKey(to='repport.Categorie')),
            ],
        ),
        migrations.AddField(
            model_name='project',
            name='conclusion',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='categorie',
            name='project',
            field=models.ForeignKey(to='repport.Project'),
        ),
    ]
