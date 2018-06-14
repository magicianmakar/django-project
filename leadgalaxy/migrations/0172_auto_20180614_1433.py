# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0171_userprofile_shopify_app_store'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shopifyordertrack',
            name='source_status_details',
            field=models.CharField(db_index=True, max_length=512, null=True, verbose_name=b'Source Status Details', blank=True),
        ),
    ]
