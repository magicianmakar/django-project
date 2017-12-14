# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0008_auto_20171019_0133'),
    ]

    operations = [
        migrations.AlterField(
            model_name='aliexpressfulfillmentcost',
            name='created_at',
            field=models.DateField(db_index=True),
        ),
        migrations.AlterField(
            model_name='aliexpressfulfillmentcost',
            name='source_id',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
        migrations.AlterIndexTogether(
            name='aliexpressfulfillmentcost',
            index_together=set([('store', 'order_id', 'source_id')]),
        ),
    ]
