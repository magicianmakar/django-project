# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0125_auto_20161110_0920'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubuserPermission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('codename', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('store', models.ForeignKey(related_name='subuser_permissions', blank=True, to='leadgalaxy.ShopifyStore', null=True, on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ('pk',),
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_permissions',
            field=models.ManyToManyField(related_name='user_profiles', to='leadgalaxy.SubuserPermission', blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='subuserpermission',
            unique_together=set([('codename', 'store')]),
        ),
    ]
