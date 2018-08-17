# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0155_shopifyordertrack_source_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FacebookAccess',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('access_token', models.CharField(max_length=255)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='FacebookAccount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_sync', models.DateField(null=True)),
                ('account_id', models.CharField(max_length=50)),
                ('account_name', models.CharField(max_length=255)),
                ('access', models.ForeignKey(related_name='accounts', to='profit_dashboard.FacebookAccess', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='FacebookInsight',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateField()),
                ('impressions', models.IntegerField(default=0)),
                ('spend', models.DecimalField(max_digits=9, decimal_places=2)),
                ('account', models.ForeignKey(related_name='insights', to='profit_dashboard.FacebookAccount', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['date'],
            },
        ),
        migrations.CreateModel(
            name='ShopifyProfit',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateField()),
                ('revenue', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('fulfillment_cost', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('other_costs', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='ShopifyProfitImportedOrder',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('profit', models.ForeignKey(related_name='imported_orders', to='profit_dashboard.ShopifyProfit', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
