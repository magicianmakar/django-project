# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyProfitImportedOrderTrack',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('profit', models.ForeignKey(related_name='imported_order_tracks', to='profit_dashboard.ShopifyProfit', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
