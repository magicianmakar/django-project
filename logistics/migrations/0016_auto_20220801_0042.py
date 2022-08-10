import json

from django.db import migrations, models


def forwards_func(apps, schema_editor):
    Order = apps.get_model('logistics', 'Order')
    for order in Order.objects.filter(is_paid=True):
        try:
            shipment = json.loads(order.shipment_data)
        except:
            continue
        order.carrier = shipment['selected_rate']['carrier']
        order.service = shipment['selected_rate']['service']
        order.save()


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0015_carriertype_logo_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='carrier',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.AddField(
            model_name='order',
            name='service',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.RunPython(forwards_func),
    ]
