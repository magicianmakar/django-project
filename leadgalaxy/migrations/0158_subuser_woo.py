# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0009_wooproduct_product_type'),
        ('leadgalaxy', '0157_auto_20170929_1415'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubuserWooPermission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('codename', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('store', models.ForeignKey(related_name='subuser_woo_permissions', to='woocommerce_core.WooStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ('pk',),
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_woo_stores',
            field=models.ManyToManyField(related_name='subuser_woo_stores', to='woocommerce_core.WooStore', blank=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_woo_permissions',
            field=models.ManyToManyField(to='leadgalaxy.SubuserWooPermission', blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='subuserwoopermission',
            unique_together=set([('codename', 'store')]),
        ),
    ]
