# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0090_auto_20160322_1557'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='boards',
            field=models.IntegerField(default=-2, help_text=b'-2: Default Plan/Bundles limit<br/>-1: Unlimited Boards'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='products',
            field=models.IntegerField(default=-2, help_text=b'-2: Default Plan/Bundles limit<br/>-1: Unlimited Products'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='stores',
            field=models.IntegerField(default=-2, help_text=b'-2: Default Plan/Bundles limit<br/>-1: Unlimited Stores'),
        ),
    ]
