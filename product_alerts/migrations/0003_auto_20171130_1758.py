# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0166_auto_20171102_2000'),
        ('product_alerts', '0002_shopifyproductchange_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductChange',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('store_type', models.CharField(default=b'shopify', max_length=255, blank=True)),
                ('data', models.TextField(default=b'', blank=True)),
                ('hidden', models.BooleanField(default=False, verbose_name=b'Archived change')),
                ('seen', models.BooleanField(default=False, verbose_name=b'User viewed the changes')),
                ('status', models.IntegerField(default=0, choices=[(0, b'Pending'), (1, b'Applied'), (2, b'Failed')])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('notified_at', models.DateTimeField(null=True, verbose_name=b'Email Notification Sate')),
                ('shopify_product', models.ForeignKey(to='leadgalaxy.ShopifyProduct')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AlterIndexTogether(
            name='shopifyproductchange',
            index_together=set([]),
        ),
        migrations.RemoveField(
            model_name='shopifyproductchange',
            name='product',
        ),
        migrations.RemoveField(
            model_name='shopifyproductchange',
            name='user',
        ),
        migrations.DeleteModel(
            name='ShopifyProductChange',
        ),
        migrations.AlterIndexTogether(
            name='productchange',
            index_together=set([('user', 'seen', 'hidden')]),
        ),
    ]
