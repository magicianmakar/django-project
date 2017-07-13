# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0149_pricemarkuprule'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='ips',
            field=models.TextField(null=True, verbose_name=b'User IPs', blank=True),
        ),
    ]
