# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0091_auto_20160322_1603'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='subuser_parent',
            field=models.ForeignKey(related_name='subuser_parent', to=settings.AUTH_USER_MODEL, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_stores',
            field=models.ManyToManyField(related_name='subuser_stores', to='leadgalaxy.ShopifyStore', blank=True),
        ),
    ]
