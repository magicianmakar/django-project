# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

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
                ('customer_name', models.CharField(default='', max_length=256, null=True, blank=True)),
                ('customer_email', models.CharField(default='', max_length=256, null=True, blank=True)),
                ('financial_status', models.CharField(default='', max_length=32, blank=True)),
                ('fulfillment_status', models.CharField(default='', max_length=32, null=True, blank=True)),
                ('note', models.TextField(default='', null=True, blank=True)),
                ('tags', models.CharField(default='', max_length=256, null=True, blank=True)),
                ('city', models.CharField(default='', max_length=64, blank=True)),
                ('zip_code', models.CharField(default='', max_length=32, blank=True)),
                ('country_code', models.CharField(default='', max_length=32, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(related_name='store', to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(related_name='user', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
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
                ('title', models.CharField(default='', max_length=256, blank=True)),
                ('price', models.FloatField()),
                ('quantity', models.IntegerField()),
                ('variant_id', models.BigIntegerField()),
                ('variant_title', models.CharField(default='', max_length=64, blank=True)),
                ('order', models.ForeignKey(to='shopify_orders.ShopifyOrder', on_delete=django.db.models.deletion.CASCADE)),
                ('product', models.ForeignKey(to='leadgalaxy.ShopifyProduct', null=True, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='ShopifySyncStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('sync_type', models.CharField(max_length=32)),
                ('sync_status', models.IntegerField(default=0, choices=[(0, 'Pending'), (1, 'Started'), (2, 'Completed'), (3, 'Unauthorized'), (4, 'Error')])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='shopifyorderline',
            unique_together=set([('order', 'line_id')]),
        ),
    ]
