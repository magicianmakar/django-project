# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    replaces = [(b'repport', '0001_initial'), (b'repport', '0002_auto_20150731_1213'), (b'repport', '0003_auto_20150731_1513'), (b'repport', '0004_auto_20150804_1428'), (b'repport', '0005_auto_20150807_0856'), (b'repport', '0006_auto_20150807_0858'), (b'repport', '0007_auto_20150809_1426'), (b'repport', '0008_project_template'), (b'repport', '0009_remove_project_template'), (b'repport', '0010_auto_20150809_1540'), (b'repport', '0011_project_template')]

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('description', models.TextField(default=b'', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Creation Date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last Update')),
                ('conclusion', models.TextField(default=b'', blank=True)),
                ('url', models.CharField(default=b'', max_length=256, blank=True)),
                ('website', models.CharField(default=b'', max_length=256, blank=True)),
                ('logo', models.CharField(default=b'', max_length=256, blank=True)),
            ],
        ),
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
                ('analysis', models.TextField(default=b'', blank=True)),
                ('recommendations', models.TextField(default=b'', blank=True)),
                ('guidelines', models.TextField(default=b'', blank=True)),
                ('action_description', models.TextField(default=b'', blank=True)),
                ('categorie', models.ForeignKey(to='repport.Categorie')),
                ('created_at', models.DateTimeField(default=datetime.datetime(2015, 7, 31, 15, 13, 12, 469006, tzinfo=utc), verbose_name=b'Creation Date', auto_now_add=True)),
                ('updated_at', models.DateTimeField(default=datetime.datetime(2015, 7, 31, 15, 13, 18, 110274, tzinfo=utc), verbose_name=b'Last Update', auto_now=True)),
                ('action_item', models.IntegerField(default=0, choices=[(1, b'Yes'), (0, b'No')])),
            ],
        ),
        migrations.AddField(
            model_name='categorie',
            name='project',
            field=models.ForeignKey(to='repport.Project'),
        ),
        migrations.AddField(
            model_name='categorie',
            name='created_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 7, 31, 15, 13, 3, 4250, tzinfo=utc), verbose_name=b'Creation Date', auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='categorie',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2015, 7, 31, 15, 13, 7, 433302, tzinfo=utc), verbose_name=b'Last Update', auto_now=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='categorie',
            name='color',
            field=models.CharField(default=b'', max_length=32, blank=True),
        ),
        migrations.AlterField(
            model_name='categorie',
            name='content_analysis',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='categorie',
            name='content_score',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.CreateModel(
            name='ProjectTemplate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('executive_summary', models.TextField(default=b'', blank=True)),
                ('scorecard', models.TextField(default=b'', blank=True)),
                ('content_analysis', models.TextField(default=b'', blank=True)),
                ('top_action_items', models.TextField(default=b'', blank=True)),
                ('report_template', models.TextField(default=b'', blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='project',
            name='template',
            field=models.ForeignKey(default=1, to='repport.ProjectTemplate'),
            preserve_default=False,
        ),
    ]
