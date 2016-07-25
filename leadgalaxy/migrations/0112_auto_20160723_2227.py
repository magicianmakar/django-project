# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0111_auto_20160629_1216'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='access_token',
            field=models.CharField(max_length=512, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='shopifystore',
            name='scope',
            field=models.CharField(max_length=512, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='shopifystore',
            name='shop',
            field=models.CharField(max_length=512, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='shopifystore',
            name='version',
            field=models.IntegerField(default=1, verbose_name=b'Store Version', choices=[(1, b'Private App'), (2, b'Shopify App')]),
        ),
    ]
