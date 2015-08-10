# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('repport', '0008_project_template'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='project',
            name='template',
        ),
    ]
