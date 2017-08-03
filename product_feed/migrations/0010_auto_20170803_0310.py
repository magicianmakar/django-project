# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0009_auto_20170411_2204'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqfeedstatus',
            name='default_product_category',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
        migrations.AddField(
            model_name='feedstatus',
            name='default_product_category',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
    ]
