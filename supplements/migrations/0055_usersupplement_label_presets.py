# Generated by Django 2.2.12 on 2020-05-15 03:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0054_labelcomment_is_private'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersupplement',
            name='label_presets',
            field=models.TextField(blank=True, default='{}'),
        ),
    ]
