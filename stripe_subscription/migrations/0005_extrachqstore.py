# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('commercehq_core', '0004_auto_20170420_2024'),
        ('stripe_subscription', '0004_auto_20160816_1515'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExtraCHQStore',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('status', models.CharField(default=b'pending', max_length=64, null=True, blank=True)),
                ('period_start', models.DateTimeField(null=True)),
                ('period_end', models.DateTimeField(null=True)),
                ('last_invoice', models.CharField(max_length=64, null=True, verbose_name=b'Last Invoice Item', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(to='commercehq_core.CommerceHQStore', on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'verbose_name': 'Extra CHQ Store',
                'verbose_name_plural': 'Extra CHQ Stores',
            },
        ),
    ]
