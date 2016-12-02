# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0009_auto_20161005_0915'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderExportLog',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('successful', models.BooleanField(default=False)),
                ('error', models.TextField(null=True, blank=True)),
                ('order_export', models.ForeignKey(to='order_exports.OrderExport')),
            ],
        ),
    ]
