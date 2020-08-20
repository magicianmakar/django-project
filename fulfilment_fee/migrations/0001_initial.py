# Generated by Django 2.2.12 on 2020-07-28 22:25

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def add_new_fee_permission(apps, schema_editor):
    AppPermission = apps.get_model("leadgalaxy", "AppPermission")

    AppPermission.objects.create(
        name='sales_fee.use',
        description='Charge configured fee on every Store transaction when set')
    AppPermission.objects.create(
        name='disabled_sales_fee.use',
        description='Override sales fee percent to zero (disable)')


def reverse_add_new_fee_permission(apps, schema_editor):
    AppPermission = apps.get_model("leadgalaxy", "AppPermission")

    AppPermission.objects.filter(
        name__in=['sales_fee.use', 'disabled_sales_fee.use']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SalesFeeConfig',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, default='', max_length=512, verbose_name='Title')),
                ('fee_percent', models.DecimalField(decimal_places=2, default=0, max_digits=9, verbose_name='Sales fee percent')),
                ('description', models.TextField(blank=True, null=True)),
            ],
        ),

        migrations.CreateModel(
            name='SaleTransactionFee',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_model', models.CharField(blank=True, default='', max_length=512, verbose_name='Which OrderTrack type this fee is related too')),
                ('source_id', models.IntegerField(verbose_name='Source Id')),
                ('fee_value', models.DecimalField(decimal_places=2, default=0, max_digits=9, verbose_name='Sales fee Value')),
                ('processed', models.BooleanField(default=False, verbose_name='Added to invoice or not')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last update')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('source_model', 'source_id')},
            },
        ),
        migrations.RunPython(add_new_fee_permission, reverse_add_new_fee_permission),
    ]
