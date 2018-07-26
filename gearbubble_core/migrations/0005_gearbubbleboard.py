# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('gearbubble_core', '0004_gearuserupload'),
    ]

    operations = [
        migrations.CreateModel(
            name='GearBubbleBoard',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('config', models.CharField(default=b'', max_length=512, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('products', models.ManyToManyField(to='gearbubble_core.GearBubbleProduct', blank=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'GearBubble Board',
                'verbose_name_plural': 'GearBubble Boards',
            },
        ),
    ]
