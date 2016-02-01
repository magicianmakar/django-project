# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0057_auto_20160130_1509'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='store',
            field=models.ForeignKey(to='leadgalaxy.ShopifyStore', null=True),
        ),
    ]
