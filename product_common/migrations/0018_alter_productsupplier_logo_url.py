# Generated by Django 3.2.14 on 2022-07-27 09:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_common', '0017_auto_20220714_1543'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productsupplier',
            name='logo_url',
            field=models.URLField(blank=True, null=True),
        ),
    ]