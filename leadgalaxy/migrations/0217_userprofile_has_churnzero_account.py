# Generated by Django 2.2.16 on 2021-01-10 02:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0216_groupplan_show_in_plod_app'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='has_churnzero_account',
            field=models.BooleanField(default=False),
        ),
    ]
