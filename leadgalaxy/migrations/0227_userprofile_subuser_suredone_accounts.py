# Generated by Django 2.2.24 on 2021-08-23 18:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('suredone_core', '__first__'),
        ('leadgalaxy', '0226_groupplan_parent_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='subuser_suredone_accounts',
            field=models.ManyToManyField(blank=True, related_name='subuser_ebay_stores', to='suredone_core.SureDoneAccount'),
        ),
    ]
