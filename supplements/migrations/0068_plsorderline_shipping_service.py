# Generated by Django 2.2.15 on 2020-09-03 23:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0067_new_mockup_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsorderline',
            name='shipping_service',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
