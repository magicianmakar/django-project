import json

import arrow
from django.db import migrations, models


def forwards_func(apps, schema_editor):
    Order = apps.get_model('logistics', 'Order')
    for order in Order.objects.filter(is_paid=True):
        try:
            shipment = json.loads(order.shipment_data)
        except:
            continue
        order.label_at = arrow.get(shipment['postage_label']['label_date']).datetime
        order.save()


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0016_auto_20220801_0042'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='label_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(forwards_func),
    ]
