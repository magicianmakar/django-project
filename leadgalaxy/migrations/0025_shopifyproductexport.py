# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0024_auto_20151215_1738'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyProductExport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('original_url', models.CharField(default=b'', max_length=512, blank=True)),
                ('shopify_id', models.BigIntegerField(default=0, verbose_name=b'Shopif Product ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
