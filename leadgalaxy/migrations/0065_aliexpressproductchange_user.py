# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0064_aliexpressproductchange'),
    ]

    operations = [
        migrations.AddField(
            model_name='aliexpressproductchange',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
