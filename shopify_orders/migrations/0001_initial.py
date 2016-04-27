# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0098_auto_20160425_1459'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyOrder',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField(unique=True)),
                ('order_number', models.IntegerField()),
                ('total_price', models.FloatField()),
                ('customer_id', models.BigIntegerField()),
                ('customer_name', models.CharField(default=b'', max_length=256, null=True, blank=True)),
                ('customer_email', models.CharField(default=b'', max_length=256, null=True, blank=True)),
                ('financial_status', models.CharField(default=b'', max_length=32, blank=True)),
                ('fulfillment_status', models.CharField(default=b'', max_length=32, null=True, blank=True)),
                ('note', models.TextField(default=b'', null=True, blank=True)),
                ('tags', models.CharField(default=b'', max_length=256, null=True, blank=True)),
                ('city', models.CharField(default=b'', max_length=64, blank=True)),
                ('zip_code', models.CharField(default=b'', max_length=32, blank=True)),
                ('country_code', models.CharField(default=b'', max_length=32, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(related_name='store', to='leadgalaxy.ShopifyStore')),
                ('user', models.ForeignKey(related_name='user', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ShopifyOrderLine',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('line_id', models.BigIntegerField()),
                ('shopify_product', models.BigIntegerField()),
                ('title', models.CharField(default=b'', max_length=256, blank=True)),
                ('price', models.FloatField()),
                ('quantity', models.IntegerField()),
                ('variant_id', models.BigIntegerField()),
                ('variant_title', models.CharField(default=b'', max_length=64, blank=True)),
                ('order', models.ForeignKey(to='shopify_orders.ShopifyOrder')),
                ('product', models.ForeignKey(to='leadgalaxy.ShopifyProduct', null=True)),
            ],
        ),
        migrations.CreateModel(
            name='ShopifySyncStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('sync_type', models.CharField(max_length=32)),
                ('sync_status', models.IntegerField(default=0, choices=[(0, b'Pending'), (1, b'Started'), (2, b'Completed'), (3, b'Unauthorized'), (4, b'Error')])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='shopifyorderline',
            unique_together=set([('order', 'line_id')]),
        ),
    ]
