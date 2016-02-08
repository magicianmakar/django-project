# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0050_planregistration_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyOrder',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('variant_id', models.BigIntegerField()),
                ('data', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
