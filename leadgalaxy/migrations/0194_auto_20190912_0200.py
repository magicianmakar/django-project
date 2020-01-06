# -*- coding: utf-8 -*-
# Generated by Django 1.11.23 on 2019-09-12 02:00
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bigcommerce_core', '0001_initial'),
        ('leadgalaxy', '0193_groupplan_free_plan'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubuserBigCommercePermission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codename', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subuser_bigcommerce_permissions', to='bigcommerce_core.BigCommerceStore')),
            ],
            options={
                'ordering': ('pk',),
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_bigcommerce_stores',
            field=models.ManyToManyField(blank=True, related_name='subuser_bigcommerce_stores', to='bigcommerce_core.BigCommerceStore'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_bigcommerce_permissions',
            field=models.ManyToManyField(blank=True, to='leadgalaxy.SubuserBigCommercePermission'),
        ),
        migrations.AlterUniqueTogether(
            name='subuserbigcommercepermission',
            unique_together=set([('codename', 'store')]),
        ),
    ]