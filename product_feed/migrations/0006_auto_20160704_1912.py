# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_feed', '0005_feedstatus_revision'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedstatus',
            name='fb_access_at',
            field=models.DateTimeField(null=True, verbose_name=b'Last Facebook Access', blank=True),
        ),
        migrations.AlterField(
            model_name='feedstatus',
            name='status',
            field=models.IntegerField(default=0, choices=[(0, b'Pending'), (1, b'Generated'), (2, b'Generating')]),
        ),
    ]
