# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('order_exports', '0018_auto_20161108_2022'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderExportVendor',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('raw_password', models.CharField(max_length=255, null=True, blank=True)),
                ('owner', models.ForeignKey(related_name='vendors', to=settings.AUTH_USER_MODEL)),
                ('user', models.OneToOneField(related_name='vendor', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='orderexport',
            name='vendor_user',
            field=models.ForeignKey(related_name='exports', on_delete=django.db.models.deletion.SET_NULL, blank=True, to='order_exports.OrderExportVendor', null=True),
        ),
    ]
