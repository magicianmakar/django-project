# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0002_shopifyprofitimportedordertrack'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyprofitimportedordertrack',
            name='source_id',
            field=models.CharField(default=b'', max_length=512, blank=True),
        ),
    ]
