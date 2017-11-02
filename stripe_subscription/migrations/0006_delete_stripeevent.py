# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stripe_subscription', '0005_extrachqstore'),
    ]

    operations = [
        migrations.DeleteModel(
            name='StripeEvent',
        ),
    ]
