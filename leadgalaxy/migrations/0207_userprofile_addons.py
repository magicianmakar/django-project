# Generated by Django 2.2.13 on 2020-06-17 20:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addons_core', '0001_initial'),
        ('leadgalaxy', '0206_groupplan_extra_store_cost'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='addons',
            field=models.ManyToManyField(blank=True, to='addons_core.Addon'),
        ),
    ]
