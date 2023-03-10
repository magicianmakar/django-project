# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-03-25 21:16
from __future__ import unicode_literals

from django.db import migrations, models


def order_existing_videos(apps, schema_editor):
    DashboardVideo = apps.get_model("leadgalaxy", "DashboardVideo")
    for idx, video in enumerate(DashboardVideo.objects.all()):
        video.display_order = idx
        video.save()


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0188_dashboardvideo'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='dashboardvideo',
            options={'ordering': ('display_order',)},
        ),
        migrations.AddField(
            model_name='dashboardvideo',
            name='display_order',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(order_existing_videos),
    ]
