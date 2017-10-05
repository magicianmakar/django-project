# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0158_subuser_woo'),
    ]

    operations = [
        migrations.AddField(
            model_name='usercompany',
            name='vat',
            field=models.CharField(default=b'', max_length=100, blank=True),
        ),
    ]
