# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.contrib.auth.models import User
from django.db import transaction

from leadgalaxy.models import SUBUSER_CHQ_STORE_PERMISSIONS


@transaction.atomic
def forward(apps, schema_editor):
    SubuserCHQPermission =  apps.get_model('leadgalaxy', 'SubuserCHQPermission')
    CommerceHQStore = apps.get_model('commercehq_core', 'CommerceHQStore')

    # Creates CHQ per store permissions
    stores = CommerceHQStore.objects.all()
    for store in stores:
        for codename, name in SUBUSER_CHQ_STORE_PERMISSIONS:
            SubuserCHQPermission.objects.create(store=store, codename=codename, name=name)

    # Grants subusers global and store permissions
    subusers = User.objects.filter(profile__subuser_parent__isnull=False)
    for subuser in subusers:
        for subuser_store in subuser.profile.subuser_chq_stores.all():
            chq_store_permissions = subuser_store.subuser_chq_permissions.all()
            subuser.profile.subuser_chq_permissions.add(*chq_store_permissions)


def backward(apps, schema_editor):
    SubuserCHQPermission = apps.get_model('leadgalaxy', 'SubuserCHQPermission')
    SubuserCHQPermission.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0141_auto_20170318_2344'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
