# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0163_auto_20171012_1553'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyordertrack',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date', db_index=True),
        ),
    ]
