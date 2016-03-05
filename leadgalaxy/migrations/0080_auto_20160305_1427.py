# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0079_groupplan_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='groupplan',
            name='slug',
            field=models.SlugField(unique=True, max_length=30, verbose_name=b'Plan Slug'),
        ),
    ]
