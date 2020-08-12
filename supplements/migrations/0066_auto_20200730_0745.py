# Generated by Django 2.2.13 on 2020-07-30 07:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0065_auto_20200729_1547'),
    ]

    operations = [
        migrations.RenameField(
            model_name='refundpayments',
            old_name='item_shipped',
            new_name='order_shipped',
        ),
        migrations.AddField(
            model_name='plsorderline',
            name='is_refunded',
            field=models.BooleanField(default=False),
        ),
    ]
