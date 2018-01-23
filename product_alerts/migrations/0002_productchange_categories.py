# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_alerts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='productchange',
            name='categories',
            field=models.CharField(default=b'', max_length=512, null=True),
        ),
    ]
