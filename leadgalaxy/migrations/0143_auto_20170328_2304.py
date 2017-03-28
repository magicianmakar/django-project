# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0142_auto_20170318_2358'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='subuser_chq_permissions',
            field=models.ManyToManyField(to='leadgalaxy.SubuserCHQPermission', blank=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='subuser_permissions',
            field=models.ManyToManyField(to='leadgalaxy.SubuserPermission', blank=True),
        ),
    ]
