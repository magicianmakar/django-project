# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0006_auto_20151030_2139'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyBoard',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(default='', max_length=512, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('products', models.ManyToManyField(to='leadgalaxy.ShopifyProduct')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
