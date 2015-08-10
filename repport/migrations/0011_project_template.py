# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0010_auto_20150809_1540'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='template',
            field=models.ForeignKey(default=1, to='repport.ProjectTemplate'),
            preserve_default=False,
        ),
    ]
