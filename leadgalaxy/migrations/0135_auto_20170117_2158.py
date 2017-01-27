# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0134_shopifyordertrack_source_status_details'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClippingMagicPlan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('allowed_credits', models.IntegerField(default=0)),
                ('amount', models.IntegerField(default=0, verbose_name=b'In USD')),
            ],
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='allowed_images',
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='api_id',
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='api_secret',
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='downloaded_images',
        ),
        migrations.AddField(
            model_name='clippingmagic',
            name='remaining_credits',
            field=models.BigIntegerField(default=0),
        ),
    ]
