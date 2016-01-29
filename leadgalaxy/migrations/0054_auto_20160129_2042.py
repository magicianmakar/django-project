# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0053_shopifyorder_user'),
    ]

    operations = [
        migrations.AlterField(
            model_name='accesstoken',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyboard',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyproductexport',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyproductexport',
            name='shopify_id',
            field=models.BigIntegerField(default=0, verbose_name=b'Shopify Product ID'),
        ),
        migrations.AlterField(
            model_name='shopifystore',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='userupload',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
    ]
