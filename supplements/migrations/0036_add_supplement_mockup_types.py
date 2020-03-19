# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-03-09 13:24
from __future__ import unicode_literals

from django.db import migrations
from supplements.models import MockupType, PLSupplement


def add_supplement_mockup_types(apps, schema_editor):
    mockup_type = MockupType.objects.get(slug='bottle')

    for supplement in PLSupplement.objects.all():
        supplement.mockup_type = mockup_type
        supplement.save()


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0035_plsupplement_mockup_type'),
    ]

    operations = [
        migrations.RunPython(add_supplement_mockup_types)
    ]
