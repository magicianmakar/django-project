# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-03-25 21:02
from __future__ import unicode_literals

from django.db import migrations, models


def create_initial_videos(apps, schema_editor):
    DashboardVideo = apps.get_model("leadgalaxy", "DashboardVideo")

    DashboardVideo.objects.create(
        url="https://player.vimeo.com/video/176344570?app_id=122963",
        title="Get To Know The Dropified Platform",
        description="This is a great place to start. After watching this you'll be well on your way to automating your life back."
    )

    DashboardVideo.objects.create(
        url="https://player.vimeo.com/video/145557224?app_id=122963",
        title="Dropified 101: Automating Products",
        description='Learn how to create Product Boards and save products to Dropified and/or your store with "1-Click".'
    )

    DashboardVideo.objects.create(
        url="https://player.vimeo.com/video/173627348?app_id=122963",
        title="Dropified 101: Automating Orders",
        description="You'll learn how to use Dropified to automate fulfilling orders, setup automated tracking and more!"
    )

    DashboardVideo.objects.create(
        url="https://player.vimeo.com/video/221659028?app_id=122963",
        title="Dropified 101: Top 5 Dropified Power Tips",
        description="We want you to get the most out of all the time saving powerful features in Dropified. Here's five tips to..."
    )


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0187_groupplan_dashboard_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='DashboardVideo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.TextField()),
                ('title', models.CharField(blank=True, max_length=255, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
        ),
        migrations.RunPython(create_initial_videos),
    ]
