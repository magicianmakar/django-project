# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('woocommerce_core', '0007_auto_20170804_2222'),
    ]

    operations = [
        migrations.CreateModel(
            name='WooBoard',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('config', models.CharField(default=b'', max_length=512, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('products', models.ManyToManyField(to='woocommerce_core.WooProduct', blank=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'verbose_name': 'WooCommerce Board',
                'verbose_name_plural': 'WooCommerce Boards',
            },
        ),
    ]
