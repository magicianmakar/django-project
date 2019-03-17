# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import multiselectfield.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0010_auto_20160128_1848'),
    ]

    operations = [
        migrations.AddField(
            model_name='sidebarlink',
            name='plans',
            field=multiselectfield.db.fields.MultiSelectField(max_length=164, null=True, choices=[('64543a8eb189bae7f9abc580cfc00f76', 'vip-elite'), ('3eccff4f178db4b85ff7245373102aec', 'elite'), ('55cb8a0ddbc9dacab8d99ac7ecaae00b', 'pro'), ('2877056b74f4683ee0cf9724b128e27b', 'basic'), ('606bd8eb8cb148c28c4c022a43f0432d', 'free')]),
        ),
    ]
