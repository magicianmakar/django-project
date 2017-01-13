# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0134_auto_20170106_1303'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='clippingmagic',
            name='allowed_credits',
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='api_id',
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='api_secret',
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='clippingmagic_plan',
        ),
        migrations.RemoveField(
            model_name='clippingmagicplan',
            name='default',
        ),
        migrations.AlterField(
            model_name='clippingmagicplan',
            name='allowed_credits',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='clippingmagicplan',
            name='amount',
            field=models.IntegerField(default=0, verbose_name=b'In USD'),
        ),
    ]
