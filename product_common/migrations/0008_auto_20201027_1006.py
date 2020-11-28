# Generated by Django 2.2.16 on 2020-10-27 10:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_common', '0007_auto_20200421_2357'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='store_type',
            field=models.CharField(choices=[('shopify', 'Shopify'), ('chq', 'CommerceHQ'), ('woo', 'WooCommerce'), ('gear', 'GearBubble'), ('gkart', 'GrooveKart'), ('bigcommerce', 'BigCommerce'), ('mybasket', 'MyBasket')], default='shopify', max_length=15),
        ),
        migrations.AlterField(
            model_name='orderline',
            name='store_type',
            field=models.CharField(choices=[('shopify', 'Shopify'), ('chq', 'CommerceHQ'), ('woo', 'WooCommerce'), ('gear', 'GearBubble'), ('gkart', 'GrooveKart'), ('bigcommerce', 'BigCommerce'), ('mybasket', 'MyBasket')], default='shopify', max_length=15),
        ),
    ]