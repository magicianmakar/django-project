# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0010_orderexportlog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderexportlog',
            name='order_export',
            field=models.ForeignKey(related_name='logs', to='order_exports.OrderExport'),
        ),
    ]
