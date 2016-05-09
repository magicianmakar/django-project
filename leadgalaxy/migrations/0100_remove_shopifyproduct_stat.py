# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0099_auto_20160509_1738'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='shopifyproduct',
            name='stat',
        ),
    ]
