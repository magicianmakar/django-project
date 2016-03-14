# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0088_auto_20160314_1347'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifystore',
            name='store_hash',
            field=models.CharField(default=b'', unique=True, max_length=50, editable=False),
        ),
    ]
