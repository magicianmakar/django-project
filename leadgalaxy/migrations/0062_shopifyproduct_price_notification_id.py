# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0061_shopifywebhook_call_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyproduct',
            name='price_notification_id',
            field=models.IntegerField(default=0),
        ),
    ]
