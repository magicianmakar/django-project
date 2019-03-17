# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0092_auto_20160331_1254'),
    ]

    operations = [
        migrations.AddField(
            model_name='planregistration',
            name='sender',
            field=models.ForeignKey(related_name='sender', verbose_name='Plan Generated By', blank=True, to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
