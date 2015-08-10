# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0004_auto_20150804_1428'),
    ]

    operations = [
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
        migrations.AlterField(
            model_name='project',
            name='conclusion',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='description',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='url',
            field=models.CharField(default=b'', max_length=256, blank=True),
        ),
        migrations.AlterField(
            model_name='project',
            name='website',
            field=models.CharField(default=b'', max_length=256, blank=True),
        ),
        migrations.AlterField(
            model_name='topic',
            name='action_description',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='topic',
            name='analysis',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='topic',
            name='guidelines',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='topic',
            name='recommendations',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
