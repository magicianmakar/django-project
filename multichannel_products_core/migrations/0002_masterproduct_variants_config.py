# Generated by Django 3.2.13 on 2022-06-10 14:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('multichannel_products_core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='masterproduct',
            name='variants_config',
            field=models.TextField(blank=True, default='{}', null=True),
        ),
    ]
