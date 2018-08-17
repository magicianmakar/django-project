# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0002_commercehqboard_config'),
        ('product_feed', '0007_feedstatus_include_variants_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommerceHQFeedStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('status', models.IntegerField(default=0, choices=[(0, b'Pending'), (1, b'Generated'), (2, b'Generating')])),
                ('revision', models.IntegerField(default=0)),
                ('all_variants', models.BooleanField(default=True)),
                ('include_variants_id', models.BooleanField(default=True)),
                ('generation_time', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(null=True, blank=True)),
                ('fb_access_at', models.DateTimeField(null=True, verbose_name=b'Last Facebook Access', blank=True)),
                ('store', models.OneToOneField(related_name='feedstatus', to='commercehq_core.CommerceHQStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
