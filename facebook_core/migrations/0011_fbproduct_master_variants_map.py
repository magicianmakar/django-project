# Generated by Django 3.2.14 on 2022-08-19 13:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facebook_core', '0010_fbproduct_master_product'),
    ]

    operations = [
        migrations.AddField(
            model_name='fbproduct',
            name='master_variants_map',
            field=models.TextField(blank=True, default='{}', null=True),
        ),
    ]