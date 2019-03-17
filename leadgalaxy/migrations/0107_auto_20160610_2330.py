# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0106_shopifyproductexport_product'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='notes',
            field=models.TextField(null=True, verbose_name='Admin Notes', blank=True),
        ),
        migrations.AddField(
            model_name='groupplan',
            name='payment_gateway',
            field=models.CharField(default='jvzoo', max_length=25, choices=[('jvzoo', 'JVZoo'), ('stripe', 'Stripe')]),
        ),
    ]
