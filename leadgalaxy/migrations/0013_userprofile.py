# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0012_groupplan'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('status', models.IntegerField(default=1, choices=[(0, 'Pending'), (1, 'Active'), (2, 'Inactive'), (3, 'Hold')])),
                ('full_name', models.CharField(default='', max_length=255, blank=True)),
                ('address1', models.CharField(default='', max_length=255, blank=True)),
                ('city', models.CharField(default='', max_length=255, blank=True)),
                ('state', models.CharField(default='', max_length=255, blank=True)),
                ('country', models.CharField(default='', max_length=255, blank=True)),
                ('user', models.OneToOneField(related_name='profile', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
