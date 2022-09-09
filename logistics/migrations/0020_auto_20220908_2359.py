# Generated by Django 3.2.13 on 2022-09-08 23:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0019_auto_20220823_0123'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='store_id',
            field=models.IntegerField(verbose_name='Store'),
        ),
        migrations.AlterField(
            model_name='order',
            name='store_order_number',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Order'),
        ),
    ]
