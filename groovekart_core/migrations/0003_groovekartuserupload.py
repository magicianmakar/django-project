# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-05-06 14:00
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('groovekart_core', '0002_groovekartproduct_config'),
    ]

    operations = [
        migrations.CreateModel(
            name='GrooveKartUserUpload',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.CharField(blank=True, default='', max_length=512, verbose_name='Upload file URL')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('product', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='groovekart_core.GrooveKartProduct')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
