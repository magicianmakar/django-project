# Generated by Django 2.2.24 on 2021-09-29 15:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('suredone_core', '0003_suredoneaccount_options_config_data'),
        ('leadgalaxy', '0230_merge_20210921_2233'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='subuser_sd_accounts',
            field=models.ManyToManyField(blank=True, related_name='subuser_sd_accounts', to='suredone_core.SureDoneAccount'),
        ),
    ]