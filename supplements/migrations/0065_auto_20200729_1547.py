# Generated by Django 2.2.12 on 2020-07-29 15:47

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0064_new_mockup_types'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='plsorderline',
            unique_together={('store_type', 'store_id', 'store_order_id', 'line_id', 'label')},
        ),
    ]