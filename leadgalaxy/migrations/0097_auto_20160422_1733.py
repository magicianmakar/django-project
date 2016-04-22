# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0096_featurebundle_hidden_from_user'),
    ]

    operations = [
        migrations.AlterField(
            model_name='planregistration',
            name='bundle',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Purchased Bundle', blank=True, to='leadgalaxy.FeatureBundle', null=True),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Purchased Plan', blank=True, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='plan_after_expire',
            field=models.ForeignKey(related_name='expire_plan', on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Plan to user after Expire Date', blank=True, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='subuser_parent',
            field=models.ForeignKey(related_name='subuser_parent', on_delete=django.db.models.deletion.SET_NULL, blank=True, to=settings.AUTH_USER_MODEL, null=True),
        ),
    ]
