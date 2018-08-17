# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('order_exports', '0002_auto_20170531_0744'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderExportFoundProduct',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('image_url', models.TextField()),
                ('title', models.TextField()),
                ('product_id', models.BigIntegerField()),
                ('order_export', models.ForeignKey(related_name='found_products', to='order_exports.OrderExport', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
        migrations.AlterModelOptions(
            name='orderexportquery',
            options={'ordering': ['-created_at']},
        ),
    ]
