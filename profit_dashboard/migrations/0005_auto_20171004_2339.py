# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0157_auto_20170929_1415'),
        ('profit_dashboard', '0004_shopifyprofitimportedordertrack_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='facebookaccess',
            name='account_ids',
            field=models.CharField(max_length=255, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='facebookaccess',
            name='campaigns',
            field=models.CharField(max_length=255, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='facebookaccess',
            name='store',
            field=models.ForeignKey(to='leadgalaxy.ShopifyStore', null=True),
        ),
        migrations.AddField(
            model_name='facebookaccount',
            name='store',
            field=models.ForeignKey(to='leadgalaxy.ShopifyStore', null=True),
        ),
    ]
