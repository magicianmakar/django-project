# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0159_usercompany_vat'),
        ('profit_dashboard', '0006_auto_20171005_1356'),
    ]

    operations = [
        migrations.CreateModel(
            name='AliexpressFulfillmentCost',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('source_id', models.CharField(default=b'', max_length=512, db_index=True, blank=True)),
                ('date', models.DateField()),
                ('shipping_cost', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('products_cost', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('total_cost', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
            ],
        ),
        migrations.CreateModel(
            name='OtherCost',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateField()),
                ('amount', models.DecimalField(default=0, max_digits=9, decimal_places=2)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
            ],
        ),
        migrations.RenameModel('FacebookInsight', 'FacebookAdCost'),
        migrations.AlterField(
            model_name='facebookadcost',
            name='account',
            field=models.ForeignKey(related_name='costs', to='profit_dashboard.FacebookAccount'),
        ),
        migrations.AddField(
            model_name='aliexpressfulfillmentcost',
            name='store',
            field=models.ForeignKey(default=1, to='leadgalaxy.ShopifyStore'),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='shopifyprofit',
            name='store',
        ),
        migrations.RemoveField(
            model_name='shopifyprofitimportedorder',
            name='profit',
        ),
        migrations.RemoveField(
            model_name='shopifyprofitimportedordertrack',
            name='profit',
        ),
        migrations.AddField(
            model_name='aliexpressfulfillmentcost',
            name='order_id',
            field=models.BigIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.DeleteModel(
            name='ShopifyProfit',
        ),
        migrations.DeleteModel(
            name='ShopifyProfitImportedOrder',
        ),
        migrations.DeleteModel(
            name='ShopifyProfitImportedOrderTrack',
        ),
    ]
