# Generated by Django 2.2.24 on 2021-09-21 22:33

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ebay_core', '0008_auto_20210921_1535'),
    ]

    operations = [
        migrations.AddField(
            model_name='ebayproduct',
            name='boards_list',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.IntegerField(), blank=True, null=True, size=None),
        ),
    ]
