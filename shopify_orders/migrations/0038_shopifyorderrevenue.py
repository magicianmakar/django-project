# Generated by Django 2.2.24 on 2022-01-20 19:57

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('leadgalaxy', '0233_auto_20211203_1823'),
        ('shopify_orders', '0037_shopifyorderlog_update_count'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyOrderRevenue',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_id', models.BigIntegerField()),
                ('currency', models.CharField(blank=True, max_length=256, null=True)),
                ('items_count', models.IntegerField()),
                ('line_items_price', models.FloatField()),
                ('shipping_price', models.FloatField()),
                ('total_price', models.FloatField()),
                ('total_price_usd', models.FloatField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='leadgalaxy.ShopifyStore')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('store', 'order_id')},
            },
        ),
    ]
