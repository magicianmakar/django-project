# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0005_commercehqproduct_bundle_map'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commercehqordertrack',
            name='source_id',
            field=models.CharField(default=b'', max_length=512, verbose_name=b'Source Order ID', db_index=True, blank=True),
        ),
    ]
