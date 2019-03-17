# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='article',
            name='slug',
            field=models.CharField(max_length=140),
        ),
        migrations.AlterField(
            model_name='article',
            name='stat',
            field=models.IntegerField(default=0, verbose_name='Publish stat', choices=[(0, 'Published'), (1, 'Draft'), (2, 'Waitting review')]),
        ),
        migrations.AlterField(
            model_name='comment',
            name='stat',
            field=models.IntegerField(default=0, verbose_name='Publish stat', choices=[(0, 'Published'), (1, 'Draft'), (2, 'Waitting review')]),
        ),
    ]
