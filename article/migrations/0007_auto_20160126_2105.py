# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0006_auto_20160126_2034'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='article',
            options={'verbose_name': 'Page', 'verbose_name_plural': 'Pages'},
        ),
        migrations.AlterModelOptions(
            name='articletag',
            options={'verbose_name': 'Page Tag', 'verbose_name_plural': 'Page Tags'},
        ),
        migrations.AlterModelOptions(
            name='sidebarlink',
            options={'ordering': ['-order', 'title'], 'verbose_name': 'Sidebar Link', 'verbose_name_plural': 'Sidebar Links'},
        ),
        migrations.RemoveField(
            model_name='articletag',
            name='sidebar',
        ),
    ]
