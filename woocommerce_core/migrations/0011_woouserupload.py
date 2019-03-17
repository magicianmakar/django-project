# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('woocommerce_core', '0010_auto_20180110_2202'),
    ]

    operations = [
        migrations.CreateModel(
            name='WooUserUpload',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('url', models.CharField(default='', max_length=512, verbose_name='Upload file URL', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('product', models.ForeignKey(to='woocommerce_core.WooProduct', null=True, on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
