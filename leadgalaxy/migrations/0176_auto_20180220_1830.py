# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0001_initial'),
        ('leadgalaxy', '0175_shopifystore_primary_location'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubuserGearPermission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('codename', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('store', models.ForeignKey(related_name='subuser_gear_permissions', to='gearbubble_core.GearBubbleStore')),
            ],
            options={
                'ordering': ('pk',),
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_gear_stores',
            field=models.ManyToManyField(related_name='subuser_gear_stores', to='gearbubble_core.GearBubbleStore', blank=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_gear_permissions',
            field=models.ManyToManyField(to='leadgalaxy.SubuserGearPermission', blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='subusergearpermission',
            unique_together=set([('codename', 'store')]),
        ),
    ]
