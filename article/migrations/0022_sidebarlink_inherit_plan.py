# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0021_article_body_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='sidebarlink',
            name='inherit_plan',
            field=models.BooleanField(default=False, verbose_name=b'Show For Subuser If Parent Can See It'),
        ),
    ]
