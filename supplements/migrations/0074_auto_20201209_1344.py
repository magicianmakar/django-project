# Generated by Django 2.2.16 on 2020-12-09 13:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('product_common', '0010_auto_20201209_1344'),
        ('supplements', '0073_auto_20201223_1128'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='plsorderline',
            name='is_refunded',
        ),
        migrations.AddField(
            model_name='payout',
            name='supplier',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='supplier_payouts', to='product_common.ProductSupplier'),
        ),
        migrations.AddField(
            model_name='plsorderline',
            name='line_payout',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payout_lines', to='supplements.Payout'),
        ),
        migrations.AddField(
            model_name='plsorderline',
            name='refund_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='plsorderline',
            name='shipping_payout',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ship_payout_lines', to='supplements.Payout'),
        ),
        migrations.AddField(
            model_name='refundpayments',
            name='shipping',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
            preserve_default=False,
        ),
    ]
