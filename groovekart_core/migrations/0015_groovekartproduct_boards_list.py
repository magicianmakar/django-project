# Generated by Django 2.2.24 on 2021-07-24 22:53

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('groovekart_core', '0014_auto_20210627_2050'),
    ]

    operations = [
        migrations.AddField(
            model_name='groovekartproduct',
            name='boards_list',
            field=django.contrib.postgres.fields.ArrayField(base_field=models.IntegerField(), blank=True, null=True, size=None),
        ),
    ]
