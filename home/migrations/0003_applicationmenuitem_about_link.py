# Generated by Django 3.2.15 on 2022-10-26 08:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0002_auto_20220118_2202'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicationmenuitem',
            name='about_link',
            field=models.URLField(default='https://www.dropified.com/dropified-apps/'),
        ),
    ]