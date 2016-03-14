# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0086_shopifyorder_auto_fulfilled'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='store_hash',
            field=models.CharField(default=b'', max_length=50, null=True, editable=False, blank=True),
        ),
    ]
