# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0070_planpayment_transaction_type'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='planpayment',
            options={'ordering': ['-created_at']},
        ),
    ]
