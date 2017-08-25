# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0150_userprofile_ips'),
        ('profit_dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyProfit',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateField()),
                ('revenue', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('fulfillment_cost', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('other_costs', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
            ],
        ),
        migrations.CreateModel(
            name='ShopifyProfitImportedOrder',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('profit', models.ForeignKey(related_name='imported_orders', to='profit_dashboard.ShopifyProfit')),
            ],
        ),
        migrations.RemoveField(
            model_name='othercost',
            name='store',
        ),
        migrations.DeleteModel(
            name='OtherCost',
        ),
    ]
