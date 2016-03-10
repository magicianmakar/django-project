# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0084_planregistration_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='planregistration',
            name='bundle',
            field=models.ForeignKey(verbose_name=b'Purchased Bundle', blank=True, to='leadgalaxy.FeatureBundle', null=True),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='plan',
            field=models.ForeignKey(verbose_name=b'Purchased Plan', blank=True, to='leadgalaxy.GroupPlan', null=True),
        ),
    ]
