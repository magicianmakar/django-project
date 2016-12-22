# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0131_shopifyproduct_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='currency_format',
            field=models.CharField(max_length=50, null=True, blank=True),
        ),
    ]
