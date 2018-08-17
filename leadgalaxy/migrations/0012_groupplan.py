# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0006_require_contenttypes_0002'),
        ('leadgalaxy', '0011_shopifyproduct_original_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='GroupPlan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(default=b'', max_length=512, verbose_name=b'Plan Title', blank=True)),
                ('montly_price', models.FloatField(default=0.0, verbose_name=b'Price Per Month')),
                ('stores', models.IntegerField(default=0)),
                ('products', models.IntegerField(default=0)),
                ('boards', models.IntegerField(default=0)),
                ('group', models.ForeignKey(to='auth.Group', on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
