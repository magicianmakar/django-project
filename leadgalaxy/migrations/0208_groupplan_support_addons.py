# Generated by Django 2.2.13 on 2020-08-07 14:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0207_userprofile_addons'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='support_addons',
            field=models.BooleanField(default=False),
        ),
    ]
