# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0143_auto_20170328_2304'),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceMarkupRule',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('min_price', models.FloatField(default=0.0)),
                ('max_price', models.FloatField(default=0.0)),
                ('markup_percent', models.FloatField(default=0.0)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
