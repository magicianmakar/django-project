# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0003_auto_20160126_1919'),
    ]

    operations = [
        migrations.CreateModel(
            name='SidebarLink',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=100)),
                ('link', models.CharField(max_length=512)),
                ('badge', models.CharField(default=b'', max_length=20, blank=True)),
            ],
            options={
                'verbose_name': 'Sidebar link',
                'verbose_name_plural': 'Sidebar links',
            },
        ),
    ]
