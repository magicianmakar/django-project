# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0020_article_style'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='body_format',
            field=models.CharField(default=b'wysiwyg', max_length=64, verbose_name=b'Article format', choices=[(b'wysiwyg', b'WYSIWYG'), (b'markdown', b'Markdown')]),
        ),
    ]
