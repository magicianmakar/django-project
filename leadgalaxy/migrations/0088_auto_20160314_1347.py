# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from hashlib import md5
import uuid


def add_store_hash(apps, schema_editor):
    ShopifyStore = apps.get_model("leadgalaxy", "ShopifyStore")

    print
    print '* Begin Hash generation for {} Stores'.format(ShopifyStore.objects.count()),

    for store in ShopifyStore.objects.all():

        if not store.store_hash:
            store.store_hash = md5(str(uuid.uuid4())).hexdigest()
            store.save()


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0087_shopifystore_store_hash'),
    ]

    operations = [
        migrations.RunPython(add_store_hash),
    ]
