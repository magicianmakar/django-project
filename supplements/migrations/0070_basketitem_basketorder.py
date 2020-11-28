# Generated by Django 2.2.16 on 2020-10-23 09:39

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):



    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('supplements', '0069_userunpaidorder'),
    ]

    operations = [
        migrations.CreateModel(
            name='BasketOrder',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(blank=True, default='', max_length=8)),
                ('order_data', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='basket_orders', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-pk'],
            },
        ),
        migrations.CreateModel(
            name='BasketItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='basket_items', to=settings.AUTH_USER_MODEL)),
                ('user_supplement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='basket_items', to='supplements.UserSupplement')),
            ],
            options={
                'ordering': ['-pk'],
            },
        ),
        migrations.AlterField(
            model_name='plsorder',
            name='store_type',
            field=models.CharField(
                choices=[('shopify', 'Shopify'), ('chq', 'CommerceHQ'), ('woo', 'WooCommerce'), ('gear', 'GearBubble'),
                         ('gkart', 'GrooveKart'), ('bigcommerce', 'BigCommerce'), ('mybasket', 'MyBasket')],
                default='shopify', max_length=15),
        ),
        migrations.AlterField(
            model_name='plsorderline',
            name='store_type',
            field=models.CharField(
                choices=[('shopify', 'Shopify'), ('chq', 'CommerceHQ'), ('woo', 'WooCommerce'), ('gear', 'GearBubble'),
                         ('gkart', 'GrooveKart'), ('bigcommerce', 'BigCommerce'), ('mybasket', 'MyBasket')],
                default='shopify', max_length=15),
        ),
    ]