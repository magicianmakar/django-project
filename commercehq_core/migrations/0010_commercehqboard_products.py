# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0009_commercehqboard'),
    ]

    operations = [
        migrations.AddField(
            model_name='commercehqboard',
            name='products',
            field=models.ManyToManyField(to='commercehq_core.CommerceHQProduct', blank=True),
        ),
    ]
