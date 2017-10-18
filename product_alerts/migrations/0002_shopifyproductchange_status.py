# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_alerts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproductchange',
            name='status',
            field=models.IntegerField(default=0, choices=[(0, b'Pending'), (1, b'Applied'), (2, b'Failed')]),
        ),
    ]
