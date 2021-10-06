# Generated by Django 2.2.24 on 2021-09-14 13:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0087_auto_20210802_1543'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='plsorder',
            options={'ordering': ('shipstation_retries',)},
        ),
        migrations.AddField(
            model_name='plsorder',
            name='shipstation_retries',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
