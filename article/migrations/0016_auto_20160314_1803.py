# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import multiselectfield.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0015_auto_20160307_1958'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sidebarlink',
            name='plans',
            field=multiselectfield.db.fields.MultiSelectField(max_length=337, choices=[(b'3fd1d6a2ee2d8154874204a08b31575f', b'Beta Elite'), (b'64543a8eb189bae7f9abc580cfc00f76', b'Vip Elite'), (b'3eccff4f178db4b85ff7245373102aec', b'Elite'), (b'b17d8eacbb02bb907c2ccc854f7c282d', b'Team Shopify'), (b'55cb8a0ddbc9dacab8d99ac7ecaae00b', b'Pro'), (b'2877056b74f4683ee0cf9724b128e27b', b'Basic'), (b'606bd8eb8cb148c28c4c022a43f0432d', b'Free'), (b'5427f85640fb78728ec7fd863db20e4c', b'JVZoo Pro Plan'), (b'3fd1d6a2djskflsdad815487weurjda08b31575f', b'JV Review Access'), (b'be2cc3908b196a573f6c079c1dd7f4bd', b'Team Shopify ePacket ID')]),
        ),
    ]
