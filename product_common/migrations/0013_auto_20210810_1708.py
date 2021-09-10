# Generated by Django 2.2.18 on 2021-08-10 17:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product_common', '0012_auto_20210114_1917'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(choices=[
                ('pending', 'Pending'),
                ('paid', 'Paid'),
                ('shipped', 'Shipped'),
                ('ship_error', 'Has Shipping Error')
            ], default='pending', max_length=10),
        ),
    ]