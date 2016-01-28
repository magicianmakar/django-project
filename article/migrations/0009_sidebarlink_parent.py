# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0008_auto_20160127_2221'),
    ]

    operations = [
        migrations.AddField(
            model_name='sidebarlink',
            name='parent',
            field=models.ForeignKey(related_name='childs', on_delete=django.db.models.deletion.SET_NULL, to='article.SidebarLink', null=True),
        ),
    ]
