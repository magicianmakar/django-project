# Generated by Django 2.2.12 on 2020-06-09 17:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0056_new_mockup_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='payout',
            name='shipping_cost',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]