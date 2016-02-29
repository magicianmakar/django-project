# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0009_sidebarlink_parent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sidebarlink',
            name='parent',
            field=models.ForeignKey(related_name='childs', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='article.SidebarLink', null=True),
        ),
    ]
