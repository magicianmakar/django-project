# Generated by Django 3.2.16 on 2022-11-22 20:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0105_shipstationaccount_labels_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsorderline',
            name='cancelled_in_shipstation',
            field=models.BooleanField(default=False),
        ),
    ]
