# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessToken',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('token', models.CharField(unique=True, max_length=512)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
