# Generated by Django 2.2.16 on 2021-01-14 19:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_common', '0011_remove_order_payout'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='amount',
            field=models.IntegerField(verbose_name='Total amount'),
        ),
    ]
