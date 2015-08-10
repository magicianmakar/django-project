# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('description', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Creation Date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last Update')),
            ],
        ),
    ]
