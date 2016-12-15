# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0129_shopifyproduct_original_data_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='currency_format',
            field=models.CharField(max_length=50, null=True, blank=True),
        ),
    ]
