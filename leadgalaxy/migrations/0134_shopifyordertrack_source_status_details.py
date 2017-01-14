# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0133_descriptiontemplate'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifyordertrack',
            name='source_status_details',
            field=models.CharField(max_length=512, null=True, verbose_name=b'Source Status Details', blank=True),
        ),
    ]
