# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LastSeen',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('module', models.CharField(default=b'default', max_length=20)),
                ('last_seen', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ('-last_seen',),
            },
        ),
        migrations.AlterUniqueTogether(
            name='lastseen',
            unique_together=set([('user', 'module')]),
        ),
    ]
