# Generated by Django 2.2.13 on 2020-07-23 00:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addons_core', '0003_addon_banner_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='addon',
            name='key_benfits',
            field=models.TextField(blank=True, default=''),
        ),
    ]