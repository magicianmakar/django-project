# Generated by Django 2.2.15 on 2020-08-18 12:20

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('addons_core', '0010_auto_20200812_1455'),
    ]

    operations = [
        migrations.RenameField(
            model_name='addon',
            old_name='key_benfits',
            new_name='key_benefits',
        ),
    ]