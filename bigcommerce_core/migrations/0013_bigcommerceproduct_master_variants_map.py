# Generated by Django 3.2.14 on 2022-08-19 13:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bigcommerce_core', '0012_bigcommerceproduct_master_product'),
    ]

    operations = [
        migrations.AddField(
            model_name='bigcommerceproduct',
            name='master_variants_map',
            field=models.TextField(blank=True, default='{}', null=True),
        ),
    ]
