# Generated by Django 2.2.12 on 2020-09-23 22:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('addons_core', '0013_auto_20200930_1638'),
    ]

    operations = [
        migrations.AddField(
            model_name='addon',
            name='action_name',
            field=models.CharField(default='Install', max_length=128),
        ),
        migrations.AddField(
            model_name='addon',
            name='action_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
