# Generated by Django 2.2.16 on 2020-12-21 21:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profits', '0008_auto_20190510_1143'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profitsync',
            name='last_sync',
            field=models.DateTimeField(),
        ),
    ]
