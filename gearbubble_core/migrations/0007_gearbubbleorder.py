# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0006_auto_20180405_1640'),
    ]

    operations = [
        migrations.CreateModel(
            name='GearBubbleOrder',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('product_id', models.BigIntegerField()),
                ('data', models.TextField(default=b'{}', blank=True)),
                ('customer_name', models.CharField(max_length=512)),
                ('customer_email', models.CharField(max_length=128)),
                ('amount', models.FloatField()),
                ('order_created_at', models.DateTimeField()),
                ('order_updated_at', models.DateTimeField()),
                ('order_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(to='gearbubble_core.GearBubbleStore')),
            ],
        ),
    ]
