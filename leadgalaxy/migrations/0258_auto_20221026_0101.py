# Generated by Django 3.2.14 on 2022-10-26 01:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0257_apppermission_notes'),
    ]

    operations = [
        migrations.AddField(
            model_name='apppermission',
            name='image_url',
            field=models.CharField(blank=True, max_length=512, null=True, verbose_name='Image URL'),
        ),
        migrations.AddField(
            model_name='apppermission',
            name='tags',
            field=models.CharField(blank=True, max_length=512, null=True, verbose_name='Tags'),
        ),
    ]
