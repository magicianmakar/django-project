# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.contrib.auth.models import User
from django.db import transaction

from leadgalaxy.models import SUBUSER_PERMISSIONS, SUBUSER_STORE_PERMISSIONS


@transaction.atomic
def forward(apps, schema_editor):
    SubuserPermission =  apps.get_model('leadgalaxy', 'SubuserPermission')
    ShopifyStore = apps.get_model('leadgalaxy', 'ShopifyStore')

    # Creates global permissions
    for codename, name in SUBUSER_PERMISSIONS:
        SubuserPermission.objects.create(codename=codename, name=name)

    # Creates per store permissions
    stores = ShopifyStore.objects.all()
    for store in stores:
        for codename, name in SUBUSER_STORE_PERMISSIONS:
            SubuserPermission.objects.create(store=store, codename=codename, name=name)

    # Grants subusers global and store permissions
    subusers = User.objects.filter(profile__subuser_parent__isnull=False)
    for subuser in subusers:
        global_permission_ids = SubuserPermission.objects.filter(store__isnull=True).values_list('pk', flat=True)
        subuser.profile.subuser_permissions.add(*global_permission_ids)
        for subuser_store in subuser.profile.subuser_stores.all():
            store_permissions = subuser_store.subuser_permissions.all()
            subuser.profile.subuser_permissions.add(*store_permissions)


def backward(apps, schema_editor):
    SubuserPermission = apps.get_model('leadgalaxy', 'SubuserPermission')
    SubuserPermission.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0126_auto_20161114_2025'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
