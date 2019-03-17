# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shopify_orders', '0019_shopifyordershippingline'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifysyncstatus',
            name='sync_status',
            field=models.IntegerField(default=0, choices=[(0, 'Pending'), (1, 'Started'), (2, 'Completed'), (3, 'Unauthorized'), (4, 'Error'), (5, 'Disabled'), (6, 'Reset')]),
        ),
    ]
