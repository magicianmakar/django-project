# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0095_auto_20160401_1527'),
    ]

    operations = [
        migrations.AddField(
            model_name='featurebundle',
            name='hidden_from_user',
            field=models.BooleanField(default=False, verbose_name=b'Hide in User Profile'),
        ),
    ]
