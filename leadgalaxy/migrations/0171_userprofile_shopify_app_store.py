# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0170_shopifystore_info'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='shopify_app_store',
            field=models.BooleanField(default=False, verbose_name=b'User Register from Shopify App Store'),
        ),
    ]
