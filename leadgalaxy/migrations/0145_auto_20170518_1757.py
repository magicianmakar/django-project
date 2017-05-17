# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0144_pricemarkuprule'),
    ]

    operations = [
        migrations.RenameField(
            model_name='pricemarkuprule',
            old_name='markup_percent',
            new_name='markup_value',
        ),
        migrations.AddField(
            model_name='pricemarkuprule',
            name='markup_type',
            field=models.CharField(default=b'margin_percent', max_length=25, choices=[(b'margin_percent', b'Increase by %'), (b'margin_amount', b'Increase by $'), (b'fixed_amount', b'Set to $')]),
        ),
    ]
