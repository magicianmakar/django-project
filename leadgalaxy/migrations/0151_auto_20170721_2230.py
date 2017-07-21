# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0150_userprofile_ips'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='monthly_price',
            field=models.DecimalField(null=True, verbose_name=b'Monthly Price(in USD)', max_digits=9, decimal_places=2),
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='payment_gateway',
            field=models.CharField(default=b'jvzoo', max_length=25, choices=[(b'jvzoo', b'JVZoo'), (b'stripe', b'Stripe'), (b'shopify', b'Shopify')]),
        ),
    ]
