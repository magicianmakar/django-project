# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0003_shopifyproduct'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='stat',
            field=models.IntegerField(default=0, verbose_name=b'Publish stat'),
        ),
    ]
