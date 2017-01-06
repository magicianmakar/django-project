# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0133_descriptiontemplate'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClippingMagicPlan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('allowed_credits', models.BigIntegerField(default=0)),
                ('amount', models.BigIntegerField(default=0)),
                ('default', models.IntegerField(default=0)),
            ],
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='allowed_images',
        ),
        migrations.RemoveField(
            model_name='clippingmagic',
            name='downloaded_images',
        ),
        migrations.AddField(
            model_name='clippingmagic',
            name='allowed_credits',
            field=models.BigIntegerField(default=-1),
        ),
        migrations.AddField(
            model_name='clippingmagic',
            name='remaining_credits',
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='clippingmagic',
            name='clippingmagic_plan',
            field=models.ForeignKey(related_name='clippingmagic_plan', blank=True, to='leadgalaxy.ClippingMagicPlan', null=True),
        ),
    ]
