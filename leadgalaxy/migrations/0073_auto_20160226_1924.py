# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0072_shopifyorder_seen'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeatureBundle',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=30, verbose_name=b'Bundle Title')),
                ('slug', models.SlugField(unique=True, max_length=30, verbose_name=b'Bundle Slug')),
                ('register_hash', models.CharField(unique=True, max_length=50)),
                ('description', models.CharField(default=b'', max_length=512, blank=True)),
                ('permissions', models.ManyToManyField(to='leadgalaxy.AppPermission', blank=True)),
            ],
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='register_hash',
            field=models.CharField(unique=True, max_length=50),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='bundles',
            field=models.ManyToManyField(to='leadgalaxy.FeatureBundle', blank=True),
        ),
    ]
