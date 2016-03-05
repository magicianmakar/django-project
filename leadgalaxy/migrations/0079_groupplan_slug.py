# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0078_auto_20160302_1811'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='slug',
            field=models.SlugField(default=b'', max_length=30, verbose_name=b'Plan Slug', blank=True),
        ),
    ]
