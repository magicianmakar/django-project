# Generated by Django 2.2.16 on 2021-01-08 15:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fulfilment_fee', '0002_saletransactionfee_currency_conversion_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='saletransactionfee',
            name='source_id',
            field=models.CharField(blank=True, default='', max_length=512, verbose_name='Source Id'),
        ),
    ]
