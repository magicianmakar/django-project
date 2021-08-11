# Generated by Django 2.2.24 on 2021-06-26 12:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0022_wooproduct_user_supplement'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wooproduct',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='wooproduct',
            name='data',
            field=models.TextField(blank=True, default='{}', null=True),
        ),
        migrations.AlterField(
            model_name='wooproduct',
            name='price',
            field=models.FloatField(default=0.0),
        ),
        migrations.AlterField(
            model_name='wooproduct',
            name='product_type',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='wooproduct',
            name='title',
            field=models.TextField(blank=True, db_index=True, null=True),
        ),
    ]