# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0093_planregistration_sender'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='subuser_parent',
            field=models.ForeignKey(related_name='subuser_parent', blank=True, to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
