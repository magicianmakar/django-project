# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('affiliations', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='leaddynoaffiliate',
            name='user',
        ),
        migrations.RemoveField(
            model_name='leaddynolead',
            name='affiliate',
        ),
        migrations.RemoveField(
            model_name='leaddynopurchase',
            name='affiliate',
        ),
        migrations.RemoveField(
            model_name='leaddynosync',
            name='last_synced_lead',
        ),
        migrations.RemoveField(
            model_name='leaddynosync',
            name='last_synced_purchase',
        ),
        migrations.RemoveField(
            model_name='leaddynosync',
            name='last_synced_visitor',
        ),
        migrations.RemoveField(
            model_name='leaddynovisitor',
            name='affiliate',
        ),
        migrations.DeleteModel(
            name='LeadDynoAffiliate',
        ),
        migrations.DeleteModel(
            name='LeadDynoLead',
        ),
        migrations.DeleteModel(
            name='LeadDynoPurchase',
        ),
        migrations.DeleteModel(
            name='LeadDynoSync',
        ),
        migrations.DeleteModel(
            name='LeadDynoVisitor',
        ),
    ]
