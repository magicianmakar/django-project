# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0003_shopifyprofitimportedordertrack_source_id'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='shopifyprofit',
            options={'ordering': ['date']},
        ),
        migrations.AddField(
            model_name='shopifyprofitimportedordertrack',
            name='amount',
            field=models.DecimalField(default=0, max_digits=9, decimal_places=2),
        ),
    ]
