# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0063_auto_20160217_0041'),
    ]

    operations = [
        migrations.CreateModel(
            name='AliexpressProductChange',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('hidden', models.BooleanField(default=False)),
                ('data', models.TextField(default=b'', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('product', models.ForeignKey(to='leadgalaxy.ShopifyProduct', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
    ]
