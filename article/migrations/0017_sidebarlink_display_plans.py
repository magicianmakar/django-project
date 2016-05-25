# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def merge_plans(apps, schema_editor):
    GroupPlan = apps.get_model("leadgalaxy", "GroupPlan")
    SidebarLink = apps.get_model("article", "SidebarLink")

    for link in SidebarLink.objects.all():
        for i in link.plans:
            try:
                plan = GroupPlan.objects.get(register_hash=i)
                link.display_plans.add(plan)
            except:
                print 'Warning: Hash not found', i


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0096_featurebundle_hidden_from_user'),
        ('article', '0016_auto_20160314_1803'),
    ]

    operations = [
        migrations.AddField(
            model_name='sidebarlink',
            name='display_plans',
            field=models.ManyToManyField(to='leadgalaxy.GroupPlan', blank=True),
        ),
        migrations.RunPython(merge_plans),
    ]
