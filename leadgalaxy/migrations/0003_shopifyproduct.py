# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0002_accesstoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyProduct',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('data', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
