# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0007_gearbubbleorder'),
        ('product_feed', '0011_woofeedstatus'),
    ]

    operations = [
        migrations.CreateModel(
            name='GearBubbleFeedStatus',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('status', models.IntegerField(default=0, choices=[(0, b'Pending'), (1, b'Generated'), (2, b'Generating')])),
                ('revision', models.IntegerField(default=0)),
                ('all_variants', models.BooleanField(default=True)),
                ('include_variants_id', models.BooleanField(default=True)),
                ('default_product_category', models.CharField(default=b'', max_length=512, blank=True)),
                ('generation_time', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(null=True, blank=True)),
                ('fb_access_at', models.DateTimeField(null=True, verbose_name=b'Last Facebook Access', blank=True)),
                ('store', models.OneToOneField(related_name='feedstatus', to='gearbubble_core.GearBubbleStore')),
            ],
            options={
                'verbose_name': 'GearBubble Feed Status',
                'verbose_name_plural': 'GearBubble Feed Statuses',
            },
        ),
    ]
