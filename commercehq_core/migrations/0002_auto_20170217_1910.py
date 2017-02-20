# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('commercehq_core', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='commercehqcollection',
            name='store',
        ),
        migrations.AlterModelOptions(
            name='commercehqproduct',
            options={'ordering': ['-created_at']},
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='auto_fulfillment',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='collections',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='compare_price',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='is_draft',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='is_template',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='options',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='product_id',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='seo_meta',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='seo_title',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='seo_url',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='shipping_weight',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='sku',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='template_name',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='textareas',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='track_inventory',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='variants',
        ),
        migrations.RemoveField(
            model_name='commercehqproduct',
            name='vendor',
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='data',
            field=models.TextField(default=b'{}', blank=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='default_supplier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='commercehq_core.CommerceHQProductSupplier', null=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='notes',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='parent_product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Dupliacte of product', blank=True, to='commercehq_core.CommerceHQProduct', null=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='source_id',
            field=models.BigIntegerField(default=0, null=True, verbose_name=b'CommerceHQ Product ID', db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='user',
            field=models.ForeignKey(default=None, to=settings.AUTH_USER_MODEL),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='commercehqproduct',
            name='price',
            field=models.FloatField(db_index=True, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='commercehqproduct',
            name='product_type',
            field=models.CharField(max_length=300, db_index=True),
        ),
        migrations.AlterField(
            model_name='commercehqproduct',
            name='tags',
            field=models.TextField(default=b'', db_index=True, blank=True),
        ),
        migrations.AlterField(
            model_name='commercehqproduct',
            name='title',
            field=models.CharField(max_length=300, db_index=True),
        ),
        migrations.DeleteModel(
            name='CommerceHQCollection',
        ),
    ]
