# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0022_auto_20151206_1330'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppPermission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=512, verbose_name=b'Permission')),
                ('description', models.CharField(default=b'', max_length=512, verbose_name=b'Permission Description', blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='groupplan',
            name='permissions',
            field=models.ManyToManyField(to='leadgalaxy.AppPermission', blank=True),
        ),
    ]
