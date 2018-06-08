# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='TapfiliateCommissions',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('commission_id', models.CharField(max_length=128, verbose_name=b'Commission ID')),
                ('conversion_id', models.CharField(max_length=128, verbose_name=b'Conversion ID')),
                ('affiliate_id', models.CharField(max_length=128, verbose_name=b'Affiliate ID')),
                ('charge_id', models.CharField(max_length=128, verbose_name=b'Stripe Charde ID')),
                ('customer_id', models.CharField(max_length=128, verbose_name=b'Stripe Customer ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
