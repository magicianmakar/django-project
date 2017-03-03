# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('commercehq_core', '0009_commercehqboard'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommerceHQOrderTrack',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('line_id', models.BigIntegerField()),
                ('shopify_status', models.CharField(default=b'', max_length=128, null=True, verbose_name=b'CHQ Fulfillment Status', blank=True)),
                ('source_id', models.BigIntegerField(default=0, verbose_name=b'Source Order ID')),
                ('source_status', models.CharField(default=b'', max_length=128, verbose_name=b'Source Order Status', blank=True)),
                ('source_tracking', models.CharField(default=b'', max_length=128, verbose_name=b'Source Tracking Number', blank=True)),
                ('source_status_details', models.CharField(max_length=512, null=True, verbose_name=b'Source Status Details', blank=True)),
                ('hidden', models.BooleanField(default=False)),
                ('seen', models.BooleanField(default=False, verbose_name=b'User viewed the changes')),
                ('auto_fulfilled', models.BooleanField(default=False, verbose_name=b'Automatically fulfilled')),
                ('check_count', models.IntegerField(default=0)),
                ('data', models.TextField(default=b'', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('status_updated_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Last Status Update')),
                ('store', models.ForeignKey(to='commercehq_core.CommerceHQStore', null=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterIndexTogether(
            name='commercehqordertrack',
            index_together=set([('store', 'order_id', 'line_id')]),
        ),
    ]
