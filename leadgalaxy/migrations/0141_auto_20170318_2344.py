# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0002_commercehqboard_config'),
        ('leadgalaxy', '0140_captchacredit_captchacreditplan'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubuserCHQPermission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('codename', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=255)),
                ('store', models.ForeignKey(related_name='subuser_chq_permissions', to='commercehq_core.CommerceHQStore', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'ordering': ('pk',),
            },
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_chq_permissions',
            field=models.ManyToManyField(related_name='user_profiles', to='leadgalaxy.SubuserCHQPermission', blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='subuserchqpermission',
            unique_together=set([('codename', 'store')]),
        ),
    ]
