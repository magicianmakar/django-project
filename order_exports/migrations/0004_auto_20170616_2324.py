# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0003_auto_20170613_1740'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderexport',
            name='starting_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='orderexportvendor',
            name='owner',
            field=models.ForeignKey(related_name='owned_vendors', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='orderexportvendor',
            name='user',
            field=models.ForeignKey(related_name='vendors', to=settings.AUTH_USER_MODEL),
        ),
    ]
