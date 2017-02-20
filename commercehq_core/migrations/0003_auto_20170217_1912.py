# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0002_auto_20170217_1910'),
    ]

    operations = [
        migrations.RenameModel('CommerceHQProductSupplier', 'CommerceHQSupplier')
    ]
