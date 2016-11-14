# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0124_auto_20161109_1852'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='shopifyordertrack',
            index_together=set([('store', 'order_id', 'line_id')]),
        ),
    ]
