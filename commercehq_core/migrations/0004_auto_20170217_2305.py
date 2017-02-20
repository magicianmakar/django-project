# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
from django.utils.timezone import utc
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('commercehq_core', '0003_auto_20170217_1912'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='commercehqproduct',
            options={'ordering': ['-created_at'], 'verbose_name': 'CHQ Product'},
        ),
        migrations.AlterModelOptions(
            name='commercehqstore',
            options={'ordering': ['-created_at'], 'verbose_name': 'CHQ Store'},
        ),
        migrations.AddField(
            model_name='commercehqstore',
            name='created_at',
            field=models.DateTimeField(default=datetime.datetime(2017, 2, 17, 23, 5, 43, 571628, tzinfo=utc), auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='commercehqstore',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2017, 2, 17, 23, 5, 50, 483477, tzinfo=utc), auto_now=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='commercehqstore',
            name='user',
            field=models.ForeignKey(default=None, to=settings.AUTH_USER_MODEL),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='commercehqstore',
            name='url',
            field=models.CharField(max_length=512),
        ),
    ]
