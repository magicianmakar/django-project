# Generated by Django 2.2.27 on 2022-03-16 03:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facebook_core', '0003_fbstore_creds'),
    ]

    operations = [
        migrations.AddField(
            model_name='fbproduct',
            name='last_export_date',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Datetime of product export to Facebook'),
        ),
    ]
