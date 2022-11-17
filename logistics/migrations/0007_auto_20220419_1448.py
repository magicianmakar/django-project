# Generated by Django 2.2.27 on 2022-04-19 14:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0006_orderitem_order_track_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='store_id',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='order',
            name='store_order_id',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='order',
            name='store_type',
            field=models.CharField(choices=[('shopify', 'Shopify'), ('chq', 'CommerceHQ'), ('woo', 'WooCommerce'), ('ebay', 'eBay'), ('fb', 'Facebook'), ('gkart', 'GrooveKart'), ('bigcommerce', 'BigCommerce')], default='shopify', max_length=15),
        ),
        migrations.AlterField(
            model_name='orderitem',
            name='order_track_id',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]