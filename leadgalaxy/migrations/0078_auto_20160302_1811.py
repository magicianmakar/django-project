# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0077_userprofile_emails'),
    ]

    operations = [
        migrations.AlterField(
            model_name='planregistration',
            name='user',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
