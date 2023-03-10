# Generated by Django 2.2.24 on 2021-09-21 15:35

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ebay_core', '0007_ebayproduct_sd_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='ebayproduct',
            name='variants_config',
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name='ebaysupplier',
            name='product',
            field=models.ForeignKey(default=None, on_delete=django.db.models.deletion.CASCADE, to='ebay_core.EbayProduct', to_field='guid'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='ebayordertrack',
            name='line_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=512, verbose_name='Variant-specific GUID'),
        ),
        migrations.AlterField(
            model_name='ebayordertrack',
            name='store',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='ebay_core.EbayStore'),
        ),
        migrations.AlterField(
            model_name='ebayproduct',
            name='default_supplier',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='ebay_core.EbaySupplier'),
        ),
        migrations.AlterField(
            model_name='ebayproduct',
            name='sd_updated_at',
            field=models.DateTimeField(null=True, verbose_name='Product last updated in the SureDone DB'),
        ),
        migrations.AlterField(
            model_name='ebayproduct',
            name='store',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='products', to='ebay_core.EbayStore'),
        ),
        migrations.AlterField(
            model_name='ebaysupplier',
            name='store',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='suppliers', to='ebay_core.EbayStore'),
        ),
        migrations.CreateModel(
            name='EbayProductVariant',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('guid', models.CharField(db_index=True, max_length=100, unique=True, verbose_name='SureDone GUID')),
                ('sku', models.CharField(db_index=True, max_length=100, verbose_name='SureDone SKU')),
                ('variant_title', models.CharField(blank=True, max_length=512, null=True)),
                ('price', models.FloatField(default=0.0)),
                ('image', models.TextField(blank=True, null=True)),
                ('supplier_sku', models.CharField(blank=True, max_length=512, null=True)),
                ('source_id', models.BigIntegerField(blank=True, db_index=True, default=0, null=True, verbose_name='eBay Product ID')),
                ('variant_data', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('default_supplier', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='ebay_core.EbaySupplier',
                                                       verbose_name='Variant-specific Supplier')),
                ('parent_product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_variants',
                                                     to='ebay_core.EbayProduct', to_field='guid', verbose_name='Parent Product')),
            ],
            options={
                'verbose_name': 'eBay Product Variant',
                'ordering': ['created_at'],
            },
        ),
    ]
