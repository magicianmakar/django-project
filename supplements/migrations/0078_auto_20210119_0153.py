# Generated by Django 2.2.16 on 2021-01-19 01:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0077_remove_plsorder_payout'),
    ]

    operations = [
        migrations.AddField(
            model_name='mockuptype',
            name='layers',
            field=models.TextField(blank=True, default='[]'),
        ),
        migrations.AddField(
            model_name='mockuptype',
            name='presets',
            field=models.TextField(blank=True, default='[]'),
        ),
    ]
