# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='feedstatus',
            name='updated_at',
            field=models.DateTimeField(null=True),
        ),
    ]
