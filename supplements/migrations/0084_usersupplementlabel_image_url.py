# Generated by Django 2.2.18 on 2021-05-12 20:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0083_auto_20210428_1144'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersupplementlabel',
            name='image_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]