# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0139_userprofile_subuser_chq_stores'),
    ]

    operations = [
        migrations.CreateModel(
            name='CaptchaCredit',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('remaining_credits', models.BigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Created date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('user', models.OneToOneField(related_name='captchacredit', to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CaptchaCreditPlan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('allowed_credits', models.IntegerField(default=0)),
                ('amount', models.IntegerField(default=0, verbose_name=b'In USD')),
            ],
        ),
    ]
