# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0006_auto_20170218_0007'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqsupplier',
            name='created_at',
            field=models.DateTimeField(default=datetime.datetime(2017, 2, 20, 20, 14, 5, 484887, tzinfo=utc), auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='commercehqsupplier',
            name='is_default',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='commercehqsupplier',
            name='product',
            field=models.ForeignKey(default=None, to='commercehq_core.CommerceHQProduct'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='commercehqsupplier',
            name='product_url',
            field=models.CharField(max_length=512, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqsupplier',
            name='shipping_method',
            field=models.CharField(max_length=512, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqsupplier',
            name='supplier_url',
            field=models.CharField(max_length=512, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqsupplier',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2017, 2, 20, 20, 14, 17, 311836, tzinfo=utc), auto_now=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='commercehqsupplier',
            name='variants_map',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='commercehqproduct',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='commercehqproduct',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name='commercehqsupplier',
            name='supplier_name',
            field=models.CharField(db_index=True, max_length=512, null=True, blank=True),
        ),
    ]
