# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0111_auto_20160629_1216'),
    ]

    operations = [
        migrations.CreateModel(
            name='StripeCustomer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('customer_id', models.CharField(verbose_name=b'Stripe Customer ID', max_length=255, null=True, editable=False)),
                ('can_trial', models.BooleanField(default=True, verbose_name=b'Can have trial')),
                ('data', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(related_name='stripe_customer', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'verbose_name': 'Customer',
                'verbose_name_plural': 'Customers',
            },
        ),
        migrations.CreateModel(
            name='StripeEvent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('event_id', models.CharField(verbose_name=b'Event ID', unique=True, max_length=255, editable=False)),
                ('event_type', models.CharField(verbose_name=b'Event Type', max_length=255, null=True, editable=False, blank=True)),
                ('data', models.TextField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Event',
                'verbose_name_plural': 'Events',
            },
        ),
        migrations.CreateModel(
            name='StripePlan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=150)),
                ('amount', models.DecimalField(verbose_name=b'Amount(in USD)', max_digits=9, decimal_places=2)),
                ('currency', models.CharField(default=b'usd', max_length=15)),
                ('retail_amount', models.DecimalField(null=True, max_digits=9, decimal_places=2)),
                ('interval', models.CharField(default=b'month', max_length=15, choices=[(b'day', b'daily'), (b'month', b'monthly'), (b'year', b'yearly'), (b'week', b'weekly')])),
                ('interval_count', models.IntegerField(default=1)),
                ('trial_period_days', models.IntegerField(default=14)),
                ('statement_descriptor', models.TextField(null=True, blank=True)),
                ('stripe_id', models.CharField(verbose_name=b'Stripe Plan ID', unique=True, max_length=255, editable=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('plan', models.OneToOneField(related_name='stripe_plan', null=True, to='leadgalaxy.GroupPlan', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'verbose_name': 'Plan',
                'verbose_name_plural': 'Plans',
            },
        ),
        migrations.CreateModel(
            name='StripeSubscription',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('subscription_id', models.CharField(verbose_name=b'Stripe Subscription ID', unique=True, max_length=255, editable=False)),
                ('status', models.CharField(verbose_name=b'Subscription Status', max_length=64, null=True, editable=False, blank=True)),
                ('data', models.TextField(null=True, blank=True)),
                ('period_start', models.DateTimeField(null=True)),
                ('period_end', models.DateTimeField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(to='leadgalaxy.GroupPlan', on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'get_latest_by': 'created_at',
                'verbose_name': 'Subscription',
                'verbose_name_plural': 'Subscriptions',
            },
        ),
    ]
