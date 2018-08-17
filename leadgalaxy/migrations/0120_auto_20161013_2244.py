# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0119_groupplan_hidden'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserCompany',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(default=b'', max_length=100, blank=True)),
                ('address_line1', models.CharField(default=b'', max_length=255, blank=True)),
                ('address_line2', models.CharField(default=b'', max_length=255, blank=True)),
                ('city', models.CharField(default=b'', max_length=100, blank=True)),
                ('state', models.CharField(default=b'', max_length=100, blank=True)),
                ('country', models.CharField(default=b'', max_length=100, blank=True)),
                ('zip_code', models.CharField(default=b'', max_length=100, blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='userprofile',
            name='company',
            field=models.ForeignKey(blank=True, to='leadgalaxy.UserCompany', null=True, on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
