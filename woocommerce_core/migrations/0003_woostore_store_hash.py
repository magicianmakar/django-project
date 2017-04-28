# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0002_auto_20170512_0648'),
    ]

    operations = [
        migrations.AddField(
            model_name='woostore',
            name='store_hash',
            field=models.CharField(default=b'', max_length=50, editable=False),
        ),
    ]
