# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0019_article_views'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='style',
            field=models.TextField(null=True, blank=True),
        ),
    ]
