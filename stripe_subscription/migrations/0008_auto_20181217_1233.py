# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-12-17 12:33
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('woocommerce_core', '0012_wooordertrack_source_type'),
        ('gearbubble_core', '0012_gearbubbleordertrack_source_type'),
        ('stripe_subscription', '0007_auto_20171229_1956'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExtraGearStore',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(blank=True, default=b'pending', max_length=64, null=True)),
                ('period_start', models.DateTimeField(null=True)),
                ('period_end', models.DateTimeField(null=True)),
                ('last_invoice', models.CharField(blank=True, max_length=64, null=True, verbose_name=b'Last Invoice Item')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extra', to='gearbubble_core.GearBubbleStore')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Extra GearBubble Store',
                'verbose_name_plural': 'Extra GearBubble Stores',
            },
        ),
        migrations.CreateModel(
            name='ExtraWooStore',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(blank=True, default=b'pending', max_length=64, null=True)),
                ('period_start', models.DateTimeField(null=True)),
                ('period_end', models.DateTimeField(null=True)),
                ('last_invoice', models.CharField(blank=True, max_length=64, null=True, verbose_name=b'Last Invoice Item')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extra', to='woocommerce_core.WooStore')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Extra WooCommerce Store',
                'verbose_name_plural': 'Extra WooCommerce Stores',
            },
        ),
        migrations.AlterField(
            model_name='extrachqstore',
            name='store',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extra', to='commercehq_core.CommerceHQStore'),
        ),
        migrations.AlterField(
            model_name='extrastore',
            name='store',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extra', to='leadgalaxy.ShopifyStore'),
        ),
    ]
