# Generated by Django 2.2.13 on 2020-07-21 15:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addons_core', '0002_addonusage'),
    ]

    operations = [
        migrations.AddField(
            model_name='addon',
            name='banner_url',
            field=models.TextField(blank=True, null=True),
        ),
    ]
