# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0020_userupload'),
    ]

    operations = [
        migrations.AddField(
            model_name='userupload',
            name='url',
            field=models.CharField(default='', max_length=512, verbose_name='Upload file URL', blank=True),
        ),
    ]
