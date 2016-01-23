# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models

import uuid, md5


def random_hash():
    token = str(uuid.uuid4())
    return md5.new(token).hexdigest()


def plans_reg_hash(apps, schema_editor):
    GroupPlan = apps.get_model("leadgalaxy", "GroupPlan")

    print
    print '* Begin Registration Hash merging for {} plans'.format(GroupPlan.objects.count())

    for plan in GroupPlan.objects.all():
        if not plan.register_hash:
            plan.register_hash = random_hash()
            plan.save()


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0047_groupplan_register_hash'),
    ]

    operations = [
        migrations.RunPython(plans_reg_hash),
    ]
