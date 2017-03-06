# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0011_commercehqboard_products'),
    ]

    operations = [
        migrations.RenameField(
            model_name='commercehqordertrack',
            old_name='shopify_status',
            new_name='commercehq_status',
        ),
    ]
