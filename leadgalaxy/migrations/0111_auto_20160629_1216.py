# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0110_remove_userprofile_stripe_customer_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='features',
            field=models.TextField(null=True, verbose_name=b'Features List', blank=True),
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='description',
            field=models.CharField(default=b'', max_length=512, verbose_name=b'Plan name visible to users', blank=True),
        ),
    ]
