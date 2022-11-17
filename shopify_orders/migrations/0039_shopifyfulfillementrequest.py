# Generated by Django 3.2.14 on 2022-11-15 14:03

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0262_auto_20221111_1742'),
        ('shopify_orders', '0038_shopifyorderrevenue'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyFulfillementRequest',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fulfillment_order_id', models.BigIntegerField()),
                ('status', models.CharField(blank=True, max_length=256, null=True)),
                ('order_id', models.BigIntegerField()),
                ('assigned_location_id', models.BigIntegerField()),
                ('data', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='leadgalaxy.shopifystore')),
            ],
            options={
                'unique_together': {('store', 'order_id')},
            },
        ),
    ]