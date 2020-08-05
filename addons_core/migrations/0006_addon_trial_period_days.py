# Generated by Django 2.2.13 on 2020-07-21 10:16

from django.db import migrations, models


def add_addons_plan(apps, schema_editor):
    CustomStripePlan = apps.get_model('stripe_subscription', 'CustomStripePlan')
    plan = CustomStripePlan()
    plan.name = "Addons Plan"
    plan.amount = 0
    plan.currency = "usd"
    plan.retail_amount = 0
    plan.interval = "month"
    plan.interval_count = 1
    plan.trial_period_days = 0
    plan.hidden = True
    plan.type = "addons_subscription"
    plan.credits_data = "{}"
    plan.stripe_id = "drop_addons"
    plan.save()


class Migration(migrations.Migration):

    dependencies = [
        ('addons_core', '0005_auto_20200716_1151'),
    ]

    operations = [
        migrations.AddField(
            model_name='addon',
            name='trial_period_days',
            field=models.IntegerField(default=0),
        ),
    ]
