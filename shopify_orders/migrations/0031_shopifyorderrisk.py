# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0164_auto_20171012_1559'),
        ('shopify_orders', '0030_auto_20171013_1630'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyOrderRisk',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('data', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
