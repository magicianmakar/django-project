# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0104_auto_20160525_1900'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproductexport',
            name='is_active',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='shopifyproductexport',
            name='supplier_name',
            field=models.CharField(default=b'', max_length=512, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='shopifyproductexport',
            name='supplier_url',
            field=models.CharField(default=b'', max_length=512, null=True, blank=True),
        ),
    ]
