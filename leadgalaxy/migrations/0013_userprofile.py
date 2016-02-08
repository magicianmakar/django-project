# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


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
                ('status', models.IntegerField(default=1, choices=[(0, b'Pending'), (1, b'Active'), (2, b'Inactive'), (3, b'Hold')])),
                ('full_name', models.CharField(default=b'', max_length=255, blank=True)),
                ('address1', models.CharField(default=b'', max_length=255, blank=True)),
                ('city', models.CharField(default=b'', max_length=255, blank=True)),
                ('state', models.CharField(default=b'', max_length=255, blank=True)),
                ('country', models.CharField(default=b'', max_length=255, blank=True)),
                ('user', models.OneToOneField(related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
