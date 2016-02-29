# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import multiselectfield.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0013_auto_20160129_0206'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sidebarlink',
            name='plans',
            field=multiselectfield.db.fields.MultiSelectField(max_length=230, choices=[(b'3fd1d6a2ee2d8154874204a08b31575f', b'Beta Elite'), (b'64543a8eb189bae7f9abc580cfc00f76', b'Vip Elite'), (b'3eccff4f178db4b85ff7245373102aec', b'Elite'), (b'b17d8eacbb02bb907c2ccc854f7c282d', b'Team Shopify'), (b'55cb8a0ddbc9dacab8d99ac7ecaae00b', b'Pro'), (b'2877056b74f4683ee0cf9724b128e27b', b'Basic'), (b'606bd8eb8cb148c28c4c022a43f0432d', b'Free')]),
        ),
    ]
