# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CommerceHQCollection',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('collection_id', models.BigIntegerField()),
                ('title', models.CharField(max_length=100)),
                ('is_auto', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='CommerceHQProduct',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('product_id', models.BigIntegerField()),
                ('title', models.CharField(max_length=300)),
                ('is_multi', models.BooleanField(default=False)),
                ('product_type', models.CharField(max_length=300)),
                ('textareas', models.TextField(default=b'', blank=True)),
                ('shipping_weight', models.FloatField(default=0.0, blank=True)),
                ('auto_fulfillment', models.BooleanField(default=False)),
                ('track_inventory', models.BooleanField(default=False)),
                ('tags', models.TextField(default=b'', blank=True)),
                ('sku', models.CharField(default=b'', max_length=200, blank=True)),
                ('seo_meta', models.TextField(default=b'', blank=True)),
                ('seo_title', models.TextField()),
                ('seo_url', models.URLField(default=b'', blank=True)),
                ('is_template', models.BooleanField(default=False)),
                ('template_name', models.CharField(default=b'', max_length=300, blank=True)),
                ('is_draft', models.BooleanField(default=False)),
                ('price', models.FloatField(null=True, blank=True)),
                ('compare_price', models.FloatField(null=True, blank=True)),
                ('options', models.TextField(null=True, blank=True)),
                ('variants', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField()),
                ('updated_at', models.DateTimeField()),
                ('collections', models.ManyToManyField(to='commercehq_core.CommerceHQCollection', blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='CommerceHQProductSupplier',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('supplier_name', models.CharField(max_length=300)),
            ],
        ),
        migrations.CreateModel(
            name='CommerceHQStore',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('url', models.URLField()),
                ('title', models.CharField(default=b'', max_length=300, blank=True)),
                ('api_key', models.CharField(max_length=300)),
                ('api_password', models.CharField(max_length=300)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'CommerceHQ Store',
            },
        ),
        migrations.AddField(
            model_name='commercehqproductsupplier',
            name='store',
            field=models.ForeignKey(related_name='suppliers', to='commercehq_core.CommerceHQStore'),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='store',
            field=models.ForeignKey(related_name='products', to='commercehq_core.CommerceHQStore'),
        ),
        migrations.AddField(
            model_name='commercehqproduct',
            name='vendor',
            field=models.ForeignKey(blank=True, to='commercehq_core.CommerceHQProductSupplier', null=True),
        ),
        migrations.AddField(
            model_name='commercehqcollection',
            name='store',
            field=models.ForeignKey(related_name='collections', to='commercehq_core.CommerceHQStore'),
        ),
    ]
