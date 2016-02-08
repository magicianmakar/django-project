# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0054_auto_20160129_2042'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyorder',
            name='source_id',
            field=models.BigIntegerField(default=0, verbose_name=b'Source Product ID'),
        ),
    ]
