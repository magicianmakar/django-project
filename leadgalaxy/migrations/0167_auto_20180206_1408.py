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
            field=models.CharField(default=b'margin_percent', max_length=25, choices=[(b'margin_percent', b'Increase by percentage'), (b'margin_amount', b'Increase by amount'), (b'fixed_amount', b'Set to fixed amount')]),
        ),
    ]
