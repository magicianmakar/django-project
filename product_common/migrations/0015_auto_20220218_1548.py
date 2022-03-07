# Generated by Django 2.2.27 on 2022-02-18 15:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_common', '0014_merge_20210921_2233'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='store_type',
            field=models.CharField(choices=[('shopify', 'Shopify'), ('chq', 'CommerceHQ'), ('woo', 'WooCommerce'), ('ebay', 'eBay'), ('fb', 'Facebook'), ('gear', 'GearBubble'), ('gkart', 'GrooveKart'), ('bigcommerce', 'BigCommerce'), ('mybasket', 'MyBasket')], default='shopify', max_length=15),
        ),
        migrations.AlterField(
            model_name='orderline',
            name='store_type',
            field=models.CharField(choices=[('shopify', 'Shopify'), ('chq', 'CommerceHQ'), ('woo', 'WooCommerce'), ('ebay', 'eBay'), ('fb', 'Facebook'), ('gear', 'GearBubble'), ('gkart', 'GrooveKart'), ('bigcommerce', 'BigCommerce'), ('mybasket', 'MyBasket')], default='shopify', max_length=15),
        ),
    ]