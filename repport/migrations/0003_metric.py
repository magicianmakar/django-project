# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0002_auto_20150811_1158'),
    ]

    operations = [
        migrations.CreateModel(
            name='Metric',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=512)),
                ('value', models.CharField(default=b'', max_length=512, blank=True)),
                ('description', models.CharField(default=b'', max_length=512, blank=True)),
                ('project', models.ForeignKey(to='repport.Project')),
            ],
        ),
    ]
