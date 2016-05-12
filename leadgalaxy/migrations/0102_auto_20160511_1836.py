# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0101_auto_20160509_2241'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ShopifyOrder',
            new_name='ShopifyOrderTrack'
        ),
    ]
