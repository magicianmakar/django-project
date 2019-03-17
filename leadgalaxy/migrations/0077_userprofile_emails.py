# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0076_userprofile_timezone'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='emails',
            field=models.TextField(default='', null=True, verbose_name='Other Emails', blank=True),
        ),
    ]
