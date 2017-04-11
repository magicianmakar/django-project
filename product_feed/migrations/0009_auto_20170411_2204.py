# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0008_commercehqfeedstatus'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='commercehqfeedstatus',
            options={'verbose_name': 'Commerce HQ Feed Status', 'verbose_name_plural': 'Commerce HQ Feed Statuses'},
        ),
        migrations.AlterModelOptions(
            name='feedstatus',
            options={'verbose_name': 'Feed Status', 'verbose_name_plural': 'Feed Statuses'},
        ),
    ]
