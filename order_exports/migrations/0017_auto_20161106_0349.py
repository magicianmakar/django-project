# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0016_auto_20161025_1817'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderExportQuery',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('code', models.CharField(max_length=50, null=True, blank=True)),
                ('params', models.TextField(default=b'')),
            ],
        ),
        migrations.AddField(
            model_name='orderexport',
            name='code',
            field=models.CharField(max_length=50, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='orderexportquery',
            name='order_export',
            field=models.ForeignKey(related_name='queries', to='order_exports.OrderExport'),
        ),
    ]
