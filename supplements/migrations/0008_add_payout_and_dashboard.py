# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-10-18 04:22
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0007_capture_store_info_and_order_key'),
    ]

    operations = [
        migrations.CreateModel(
            name='Payout',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference_number', models.CharField(max_length=10)),
                ('status', models.CharField(choices=[('paid', 'Paid'), ('pending', 'Pending')], default='pending', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(
            model_name='plsorder',
            name='order_number',
            field=models.CharField(default='', max_length=50),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='plsorder',
            name='status',
            field=models.CharField(choices=[('paid', 'Paid'), ('pending', 'Pending'), ('shipped', 'Shipped')], default='pending', max_length=10),
        ),
        migrations.AddField(
            model_name='plsorder',
            name='payout',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payout_items', to='supplements.Payout'),
        ),
    ]