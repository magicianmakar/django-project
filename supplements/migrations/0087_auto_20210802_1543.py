# Generated by Django 2.2.18 on 2021-08-02 15:43

from django.db import migrations, models


def save_supplement_title(apps, schema_editor):
    PLSOrderLine = apps.get_model('supplements', 'PLSOrderLine')
    PLSOrderLine.objects.all().update(title=models.Subquery(
        PLSOrderLine.objects.filter(id=models.OuterRef('id')).values('label__user_supplement__title')[:1]
    ))


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0086_auto_20210526_2130'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsorder',
            name='billing_address',
            field=models.TextField(blank=True, default='{}', null=True),
        ),
        migrations.AddField(
            model_name='plsorder',
            name='shipping_address',
            field=models.TextField(blank=True, default='{}', null=True),
        ),
        migrations.AddField(
            model_name='plsorderline',
            name='shipping_service_id',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='plsorderline',
            name='title',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='plsorder',
            name='status',
            field=models.CharField(choices=[
                ('pending', 'Pending'),
                ('paid', 'Paid'),
                ('shipped', 'Shipped'),
                ('ship_error', 'Has Shipping Error')
            ], default='pending', max_length=10),
        ),
        migrations.RunPython(save_supplement_title, reverse_func),
    ]
