# Generated by Django 2.2.13 on 2020-09-21 15:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fulfilment_fee', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='saletransactionfee',
            name='currency_conversion_data',
            field=models.TextField(blank=True, null=True),
        ),
    ]
