# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0001_initial'),
        ('leadgalaxy', '0155_shopifyordertrack_source_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='subuser_woo_stores',
            field=models.ManyToManyField(related_name='subuser_woo_stores', to='woocommerce_core.WooStore', blank=True),
        ),
    ]
