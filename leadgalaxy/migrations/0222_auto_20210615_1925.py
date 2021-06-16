# Generated by Django 2.2.18 on 2021-06-15 19:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0221_groupplan_single_charge'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='label_upload_limit',
            field=models.IntegerField(default=-1, verbose_name='Label Upload Limit per month'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='label_upload_limit',
            field=models.IntegerField(default=-2),
        ),
    ]
