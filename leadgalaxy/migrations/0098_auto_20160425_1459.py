# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0097_auto_20160422_1733'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='shopifywebhook',
            unique_together=set([('store', 'topic')]),
        ),
    ]
