# Generated by Django 2.2.24 on 2021-06-26 12:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bigcommerce_core', '0006_bigcommerceproduct_user_supplement'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bigcommerceproduct',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='bigcommerceproduct',
            name='data',
            field=models.TextField(blank=True, default='{}', null=True),
        ),
        migrations.AlterField(
            model_name='bigcommerceproduct',
            name='price',
            field=models.FloatField(default=0.0),
        ),
        migrations.AlterField(
            model_name='bigcommerceproduct',
            name='product_type',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='bigcommerceproduct',
            name='title',
            field=models.TextField(blank=True, db_index=True, null=True),
        ),
    ]
