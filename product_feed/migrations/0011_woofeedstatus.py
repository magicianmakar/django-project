# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0009_wooproduct_product_type'),
        ('product_feed', '0010_auto_20170803_0310'),
    ]

    operations = [
        migrations.CreateModel(
            name='WooFeedStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('status', models.IntegerField(default=0, choices=[(0, 'Pending'), (1, 'Generated'), (2, 'Generating')])),
                ('revision', models.IntegerField(default=0)),
                ('all_variants', models.BooleanField(default=True)),
                ('include_variants_id', models.BooleanField(default=True)),
                ('default_product_category', models.CharField(default='', max_length=512, blank=True)),
                ('generation_time', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(null=True, blank=True)),
                ('fb_access_at', models.DateTimeField(null=True, verbose_name='Last Facebook Access', blank=True)),
                ('store', models.OneToOneField(related_name='feedstatus', to='woocommerce_core.WooStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'verbose_name': 'WooCommerce Feed Status',
                'verbose_name_plural': 'WooCommerce Feed Statuses',
            },
        ),
    ]
