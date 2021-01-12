# Generated by Django 2.2.16 on 2020-12-18 00:36

from django.db import migrations


def forward(apps, schema_editor):
    Addon = apps.get_model("addons_core", "Addon")
    addons = Addon.objects.all()

    for addon in addons:
        addon.churnzero_name = addon.title
        addon.save()


def backward(apps, schema_editor):
    Addon = apps.get_model("addons_core", "Addon")
    addons = Addon.objects.all()

    for addon in addons:
        addon.churnzero_name = ''
        addon.save()


class Migration(migrations.Migration):

    dependencies = [
        ('addons_core', '0017_addon_churnzero_name'),
    ]

    operations = [
        migrations.RunPython(forward, backward)
    ]
