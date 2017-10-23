# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profit_dashboard', '0007_auto_20171012_0616'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='aliexpressfulfillmentcost',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterModelOptions(
            name='facebookadcost',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterModelOptions(
            name='othercost',
            options={'ordering': ['-date']},
        ),
        migrations.RenameField(
            model_name='aliexpressfulfillmentcost',
            old_name='date',
            new_name='created_at',
        ),
        migrations.RenameField(
            model_name='facebookadcost',
            old_name='date',
            new_name='created_at',
        ),
    ]
