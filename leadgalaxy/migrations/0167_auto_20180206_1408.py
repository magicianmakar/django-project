# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0166_userprofile_sync_delay_notify'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pricemarkuprule',
            name='markup_type',
            field=models.CharField(default='margin_percent', max_length=25, choices=[('margin_percent', 'Increase by percentage'), ('margin_amount', 'Increase by amount'), ('fixed_amount', 'Set to fixed amount')]),
        ),
    ]
