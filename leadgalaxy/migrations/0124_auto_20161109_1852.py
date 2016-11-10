# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0123_auto_20161101_1829'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='aliexpressproductchange',
            index_together=set([('user', 'seen', 'hidden')]),
        ),
    ]
