# Generated by Django 2.2.12 on 2020-04-24 01:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0047_plsorderline_tracking_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsupplement',
            name='approved_label_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]
