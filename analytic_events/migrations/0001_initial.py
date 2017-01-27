# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='BillingInformationEntryEvent',
            fields=[
                ('event_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='analytic_events.Event')),
                ('source', models.TextField()),
            ],
            options={
                'abstract': False,
            },
            bases=('analytic_events.event',),
        ),
        migrations.CreateModel(
            name='PlanSelectionEvent',
            fields=[
                ('event_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='analytic_events.Event')),
            ],
            options={
                'abstract': False,
            },
            bases=('analytic_events.event',),
        ),
        migrations.CreateModel(
            name='RegistrationEvent',
            fields=[
                ('event_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='analytic_events.Event')),
            ],
            options={
                'abstract': False,
            },
            bases=('analytic_events.event',),
        ),
        migrations.CreateModel(
            name='SuccessfulPaymentEvent',
            fields=[
                ('event_ptr', models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False, to='analytic_events.Event')),
                ('charge', models.TextField()),
            ],
            options={
                'abstract': False,
            },
            bases=('analytic_events.event',),
        ),
        migrations.AddField(
            model_name='event',
            name='polymorphic_ctype',
            field=models.ForeignKey(related_name='polymorphic_analytic_events.event_set+', editable=False, to='contenttypes.ContentType', null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
        ),
    ]
