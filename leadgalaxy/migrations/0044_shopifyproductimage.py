# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0043_auto_20160104_1730'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyProductImage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('product', models.BigIntegerField(verbose_name=b'Shopify Product ID')),
                ('variant', models.BigIntegerField(default=0, verbose_name=b'Shopify Product ID')),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
