# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0001_initial'),
        ('leadgalaxy', '0147_auto_20170601_1554'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='subuser_woo_stores',
            field=models.ManyToManyField(related_name='subuser_woo_stores', to='woocommerce_core.WooStore', blank=True),
        ),
    ]
