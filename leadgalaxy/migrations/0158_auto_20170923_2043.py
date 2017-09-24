# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('woocommerce_core', '0009_wooproduct_product_type'),
        ('leadgalaxy', '0157_userprofile_subuser_woo_stores'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubuserWooPermission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('codename', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('store', models.ForeignKey(related_name='subuser_woo_permissions', to='woocommerce_core.WooStore')),
            ],
            options={
                'ordering': ('pk',),
            },
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
