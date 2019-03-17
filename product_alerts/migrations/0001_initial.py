# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0007_commercehqproduct_monitor_id'),
        ('leadgalaxy', '0165_shopifyproduct_monitor_id'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductChange',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('store_type', models.CharField(default='shopify', max_length=255, blank=True)),
                ('data', models.TextField(default='', blank=True)),
                ('hidden', models.BooleanField(default=False, verbose_name='Archived change')),
                ('seen', models.BooleanField(default=False, verbose_name='User viewed the changes')),
                ('status', models.IntegerField(default=0, choices=[(0, 'Pending'), (1, 'Applied'), (2, 'Failed')])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('notified_at', models.DateTimeField(null=True, verbose_name='Email Notification Sate')),
                ('chq_product', models.ForeignKey(to='commercehq_core.CommerceHQProduct', null=True, on_delete=django.db.models.deletion.CASCADE)),
                ('shopify_product', models.ForeignKey(to='leadgalaxy.ShopifyProduct', null=True, on_delete=django.db.models.deletion.CASCADE)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AlterIndexTogether(
            name='productchange',
            index_together=set([('user', 'seen', 'hidden')]),
        ),
    ]
