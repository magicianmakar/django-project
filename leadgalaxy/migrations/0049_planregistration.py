# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0048_auto_20160123_1704'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanRegistration',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('register_hash', models.CharField(unique=True, max_length=40)),
                ('data', models.CharField(default=b'', max_length=512, blank=True)),
                ('expired', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('plan', models.ForeignKey(to='leadgalaxy.GroupPlan')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
