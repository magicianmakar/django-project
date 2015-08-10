# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0006_auto_20150807_0858'),
    ]

    operations = [
        migrations.CreateModel(
            name='Template',
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
        migrations.AlterField(
            model_name='topic',
            name='action_item',
            field=models.IntegerField(default=0, choices=[(1, b'Yes'), (0, b'No')]),
        ),
    ]
