# Generated by Django 2.2.16 on 2021-03-29 19:58

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0081_auto_20210312_2329'),
    ]

    operations = [
        migrations.AddField(
            model_name='refundpayments',
            name='status',
            field=models.CharField(choices=[('refunded', 'Refunded'), ('voided', 'Voided')], default='refunded', max_length=8),
        ),
    ]
