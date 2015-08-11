# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0001_squashed_0011_project_template'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='projecttemplate',
            name='content_analysis',
        ),
        migrations.RemoveField(
            model_name='projecttemplate',
            name='executive_summary',
        ),
        migrations.RemoveField(
            model_name='projecttemplate',
            name='scorecard',
        ),
        migrations.RemoveField(
            model_name='projecttemplate',
            name='top_action_items',
        ),
        migrations.AddField(
            model_name='projecttemplate',
            name='report_style',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='topic',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Creation Date'),
        ),
        migrations.AlterField(
            model_name='topic',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, verbose_name=b'Last Update'),
        ),
    ]
