# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0148_productsupplier_notes'),
    ]

    operations = [
        migrations.CreateModel(
            name='PriceMarkupRule',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255, null=True, blank=True)),
                ('min_price', models.FloatField(default=0.0)),
                ('max_price', models.FloatField(default=0.0)),
                ('markup_value', models.FloatField(default=0.0)),
                ('markup_compare_value', models.FloatField(default=0.0)),
                ('markup_type', models.CharField(default=b'margin_percent', max_length=25, choices=[(b'margin_percent', b'Increase by pecenatge'), (b'margin_amount', b'Increase by amount'), (b'fixed_amount', b'Set to fixed amount')])),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE)),
            ],
        ),
    ]
