# Generated by Django 2.2.24 on 2021-11-30 13:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0231_userprofile_subuser_sd_accounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopifystore',
            name='hubspot_title',
            field=models.CharField(blank=True, default='', max_length=512),
        ),
    ]
