# Generated by Django 2.2.24 on 2021-06-27 20:50

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0223_auto_20210626_1250'),
    ]

    operations = [
        migrations.RenameField(
            model_name='shopifyproduct',
            old_name='tag',
            new_name='tags',
        ),
    ]
