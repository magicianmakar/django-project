# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0005_sidebarlink_order'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='sidebarlink',
            options={'ordering': ['-order', 'title'], 'verbose_name': 'Sidebar link', 'verbose_name_plural': 'Sidebar links'},
        ),
    ]
