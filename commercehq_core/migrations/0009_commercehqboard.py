# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('commercehq_core', '0008_auto_20170302_1818'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommerceHQBoard',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=512)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'CHQ Board',
                'verbose_name_plural': 'CHQ Boards',
            },
        ),
    ]
