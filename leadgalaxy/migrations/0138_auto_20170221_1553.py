# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0137_auto_20170215_1735'),
    ]

    operations = [
        migrations.AddField(
            model_name='aliexpressproductchange',
            name='notified_at',
            field=models.DateTimeField(null=True, verbose_name=b'Email Notification Sate'),
        ),
        migrations.AlterField(
            model_name='aliexpressproductchange',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='aliexpressproductchange',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
