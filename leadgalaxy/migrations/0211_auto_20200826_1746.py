# Generated by Django 2.2.15 on 2020-08-26 17:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0210_groupplan_sales_fee_config'),
    ]

    operations = [
        migrations.AlterField(
            model_name='groupplan',
            name='sales_fee_config',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='fulfilment_fee.SalesFeeConfig'),
        ),
    ]
