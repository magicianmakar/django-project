# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0073_auto_20160226_1924'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='plan_after_expire',
            field=models.ForeignKey(related_name='expire_plan', verbose_name=b'Plan to user after Expire Date', blank=True, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='plan_expire_at',
            field=models.DateTimeField(null=True, verbose_name=b'Plan Expire Date', blank=True),
        ),
    ]
