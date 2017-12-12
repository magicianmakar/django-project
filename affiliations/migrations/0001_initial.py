# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LeadDynoAffiliate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('affiliation_id', models.BigIntegerField()),
                ('email', models.CharField(max_length=255)),
                ('first_name', models.CharField(default=b'', max_length=255, null=True)),
                ('last_name', models.CharField(default=b'', max_length=255, null=True)),
                ('affiliate_dashboard_url', models.CharField(max_length=512)),
                ('affiliate_url', models.CharField(max_length=512)),
                ('user', models.OneToOneField(related_name='lead_dyno_affiliation', null=True, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='LeadDynoLead',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('affiliate_email', models.CharField(default=b'', max_length=255)),
                ('original_data', models.TextField()),
                ('lead_id', models.BigIntegerField()),
                ('email', models.CharField(default=b'', max_length=512, blank=True)),
                ('created_at', models.DateTimeField()),
                ('affiliate', models.ForeignKey(related_name='leads', on_delete=django.db.models.deletion.SET_NULL, to='affiliations.LeadDynoAffiliate', null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LeadDynoPurchase',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('affiliate_email', models.CharField(default=b'', max_length=255)),
                ('original_data', models.TextField()),
                ('purchase_id', models.BigIntegerField()),
                ('purchase_code', models.CharField(max_length=100)),
                ('created_at', models.DateTimeField()),
                ('affiliate', models.ForeignKey(related_name='purchases', on_delete=django.db.models.deletion.SET_NULL, to='affiliations.LeadDynoAffiliate', null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LeadDynoSync',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('count_visitors', models.IntegerField(default=0)),
                ('count_leads', models.IntegerField(default=0)),
                ('count_purchases', models.IntegerField(default=0)),
                ('last_synced_lead', models.ForeignKey(to='affiliations.LeadDynoLead', null=True)),
                ('last_synced_purchase', models.ForeignKey(to='affiliations.LeadDynoPurchase', null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LeadDynoVisitor',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('affiliate_email', models.CharField(default=b'', max_length=255)),
                ('original_data', models.TextField()),
                ('visitor_id', models.BigIntegerField()),
                ('created_at', models.DateTimeField()),
                ('tracking_code', models.CharField(max_length=64)),
                ('url', models.CharField(max_length=512)),
                ('affiliate', models.ForeignKey(related_name='visitors', on_delete=django.db.models.deletion.SET_NULL, to='affiliations.LeadDynoAffiliate', null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='leaddynosync',
            name='last_synced_visitor',
            field=models.ForeignKey(to='affiliations.LeadDynoVisitor', null=True),
        ),
    ]
