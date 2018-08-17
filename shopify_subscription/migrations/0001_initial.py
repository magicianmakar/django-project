# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0151_auto_20170721_2230'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifySubscription',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('subscription_id', models.CharField(unique=True, max_length=255, verbose_name=b'Shopify Charge ID')),
                ('status', models.CharField(max_length=64, null=True, verbose_name=b'Shopify Charge Status', blank=True)),
                ('data', models.TextField(null=True, blank=True)),
                ('activated_on', models.DateTimeField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(to='leadgalaxy.GroupPlan', null=True, on_delete=django.db.models.deletion.CASCADE)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore', on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'get_latest_by': 'created_at',
                'verbose_name': 'Subscription',
                'verbose_name_plural': 'Subscriptions',
            },
        ),
    ]
