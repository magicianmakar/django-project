# Generated by Django 2.2.24 on 2021-06-26 16:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bigcommerce_core', '0008_auto_20210626_1413'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bigcommercesupplier',
            name='store',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='suppliers', to='bigcommerce_core.BigCommerceStore'),  # noqa
        ),
    ]
