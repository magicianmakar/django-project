# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0007_auto_20170220_2014'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqproduct',
            name='config',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='mapping_config',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='shipping_map',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='supplier_map',
            field=models.TextField(default=b'', null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='variants_map',
            field=models.TextField(default=b'', blank=True),
        ),
    ]
