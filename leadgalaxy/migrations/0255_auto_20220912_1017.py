# Generated by Django 3.2.14 on 2022-09-12 10:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0254_groupplan_product_create_limit'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='suredone_stores',
            field=models.IntegerField(default=0, verbose_name='SureDone Channels Limit'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='suredone_stores',
            field=models.IntegerField(default=-2),
        ),
    ]
