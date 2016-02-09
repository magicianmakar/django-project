# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0059_shopifyorder_hidden'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyWebhook',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('topic', models.CharField(max_length=64)),
                ('token', models.CharField(max_length=64)),
                ('shopify_id', models.BigIntegerField(default=0, verbose_name=b'Webhook Shopify ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
