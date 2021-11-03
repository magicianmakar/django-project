# Generated by Django 2.2.24 on 2021-09-06 14:30

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('suredone_core', '0001_initial'),
        ('ebay_core', '0004_auto_20210828_2148'),
    ]

    operations = [
        migrations.AddField(
            model_name='ebayproduct',
            name='sd_account',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='products',
                                    to='suredone_core.SureDoneAccount'),
        ),
        migrations.AlterField(
            model_name='ebayordertrack',
            name='store',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='ebay_core.EbayStore'),
        ),
        migrations.AlterField(
            model_name='ebayproduct',
            name='store',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='products',
                                    to='ebay_core.EbayStore'),
        ),
        migrations.AlterField(
            model_name='ebaystore',
            name='store_instance_id',
            field=models.IntegerField(db_index=True, editable=False, verbose_name="Store's instance ID"),
        ),
        migrations.AlterField(
            model_name='ebaysupplier',
            name='store',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='suppliers',
                                    to='ebay_core.EbayStore'),
        ),
    ]