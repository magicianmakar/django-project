# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0065_aliexpressproductchange_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='aliexpressproductchange',
            name='seen',
            field=models.BooleanField(default=False, verbose_name=b'User viewed the changes'),
        ),
        migrations.AlterField(
            model_name='aliexpressproductchange',
            name='hidden',
            field=models.BooleanField(default=False, verbose_name=b'Archived change'),
        ),
    ]
