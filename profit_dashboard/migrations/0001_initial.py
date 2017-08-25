# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0150_userprofile_ips'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='FacebookAccess',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('access_token', models.CharField(max_length=255)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='FacebookAccount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('last_sync', models.DateField(null=True)),
                ('account_id', models.CharField(max_length=50)),
                ('account_name', models.CharField(max_length=255)),
                ('access', models.ForeignKey(related_name='accounts', to='profit_dashboard.FacebookAccess')),
            ],
        ),
        migrations.CreateModel(
            name='FacebookInsight',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateField()),
                ('impressions', models.IntegerField(default=0)),
                ('spend', models.DecimalField(max_digits=9, decimal_places=2)),
                ('account', models.ForeignKey(related_name='insights', to='profit_dashboard.FacebookAccount')),
            ],
            options={
                'ordering': ['date'],
            },
        ),
        migrations.CreateModel(
            name='OtherCost',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('amount', models.FloatField()),
                ('date', models.DateField()),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
            ],
        ),
    ]
