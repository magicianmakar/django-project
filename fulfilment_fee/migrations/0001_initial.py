# Generated by Django 2.2.15 on 2020-08-20 12:29

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

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
    ]