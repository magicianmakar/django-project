# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stripe_subscription', '0006_delete_stripeevent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='stripecustomer',
            name='customer_id',
            field=models.CharField(max_length=255, null=True, verbose_name=b'Stripe Customer ID'),
        ),
    ]
