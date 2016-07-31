# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0106_shopifyproductexport_product'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductRevision',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('shopify_id', models.BigIntegerField(default=0)),
                ('data', models.TextField(default=b'', blank=True)),
                ('created_at', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(to='leadgalaxy.ShopifyProduct')),
                ('product_change', models.ForeignKey(to='leadgalaxy.AliexpressProductChange')),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
            ],
        ),
    ]
