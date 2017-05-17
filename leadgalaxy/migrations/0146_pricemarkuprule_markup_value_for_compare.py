# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
from django.db import migrations, models

from leadgalaxy.utils import safeFloat


def calc_auto_margin(apps, schema_editor):
    PriceMarkupRule = apps.get_model('leadgalaxy', 'PriceMarkupRule')
    UserProfile = apps.get_model('leadgalaxy', 'UserProfile')

    for user_profile in UserProfile.objects.all():
        config = {}
        try:
            config = json.loads(user_profile.config)
        except:
            config = {}
        print config
        if config.get('auto_margin', '') or config.get('auto_compare_at', ''):
            PriceMarkupRule.objects.create(
                user=user_profile.user,
                name='All',
                min_price=0,
                max_price=-1,
                markup_type='margin_percent',
                markup_value=safeFloat(config.get('auto_margin', '')),
                markup_value_for_compare=safeFloat(config.get('auto_compare_at', '')),
            )


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0145_auto_20170518_1757'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricemarkuprule',
            name='markup_value_for_compare',
            field=models.FloatField(default=0.0),
        ),
        migrations.RunPython(
            calc_auto_margin,
            reverse_code=migrations.RunPython.noop
        )
    ]
