# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0006_auto_20170218_0007'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommerceHQCollection',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('collection_id', models.BigIntegerField()),
                ('title', models.CharField(max_length=100)),
                ('is_auto', models.BooleanField(default=False)),
                ('store', models.ForeignKey(related_name='collections', to='commercehq_core.CommerceHQStore')),
            ],
        ),
    ]
