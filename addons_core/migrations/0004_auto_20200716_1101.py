# Generated by Django 2.2.13 on 2020-07-16 11:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addons_core', '0003_addonusage_processed'),
    ]

    operations = [
        migrations.AlterField(
            model_name='addonusage',
            name='processed',
            field=models.BooleanField(default=False, verbose_name='Invoiced'),
        ),
    ]
