# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0007_auto_20170220_2014'),
        ('leadgalaxy', '0138_auto_20170221_1553'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='subuser_chq_stores',
            field=models.ManyToManyField(related_name='subuser_chq_stores', to='commercehq_core.CommerceHQStore', blank=True),
        ),
    ]
