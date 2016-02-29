# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0033_remove_shopifyproduct_original_data'),
    ]

    operations = [
        migrations.RenameField(
            model_name='shopifyproduct',
            old_name='original_dataz',
            new_name='original_data',
        ),
    ]
