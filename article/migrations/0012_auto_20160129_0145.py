# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import multiselectfield.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0011_sidebarlink_plans'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sidebarlink',
            name='plans',
            field=multiselectfield.db.fields.MultiSelectField(default='', max_length=164, choices=[(b'64543a8eb189bae7f9abc580cfc00f76', b'vip-elite'), (b'3eccff4f178db4b85ff7245373102aec', b'elite'), (b'55cb8a0ddbc9dacab8d99ac7ecaae00b', b'pro'), (b'2877056b74f4683ee0cf9724b128e27b', b'basic'), (b'606bd8eb8cb148c28c4c022a43f0432d', b'free')]),
            preserve_default=False,
        ),
    ]
