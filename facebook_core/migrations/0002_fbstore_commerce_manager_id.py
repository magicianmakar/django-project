# Generated by Django 2.2.25 on 2022-02-16 02:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facebook_core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='fbstore',
            name='commerce_manager_id',
            field=models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Facebook Commerce Manager ID'),
        ),
    ]
