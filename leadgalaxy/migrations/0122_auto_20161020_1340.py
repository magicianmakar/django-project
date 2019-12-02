# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json

from django.db import migrations


def set_auto_fulfill(apps, schema_editor):
    UserProfile = apps.get_model("leadgalaxy", "UserProfile")

    for profile in UserProfile.objects.filter(subuser_parent=None):
        try:
            config = json.loads(profile.config)
        except:
            config = {}

        profile.user.shopifystore_set.all().update(
            auto_fulfill=config.get('auto_shopify_fulfill', '')
        )


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0121_shopifystore_auto_fulfill'),
    ]

    operations = [
        migrations.RunPython(set_auto_fulfill),
    ]
