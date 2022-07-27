# Generated by Django 2.2.27 on 2022-04-06 03:57

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
            name='Account',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_id', models.CharField(blank=True, max_length=64, null=True)),
                ('source_data', models.TextField(blank=True, default='')),
                ('api_key', models.CharField(blank=True, default='', max_length=255)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logistics_accounts',
                                           to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Listing',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inventory', models.IntegerField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('to_address_hash', models.CharField(max_length=255)),
                ('to_address', models.TextField(default='{}')),
                ('from_address', models.TextField(default='{}')),
                ('weight', models.DecimalField(decimal_places=3, default=0, max_digits=6, verbose_name='Weight (oz)')),
                ('length', models.DecimalField(decimal_places=3, default=0, max_digits=6,
                                               verbose_name='Length (inches)')),
                ('width', models.DecimalField(decimal_places=3, default=0, max_digits=6,
                                              verbose_name='Width (inches)')),
                ('height', models.DecimalField(decimal_places=3, default=0, max_digits=6,
                                               verbose_name='Height (inches)')),
                ('shipment_data', models.TextField(default='{}')),
                ('rate_id', models.CharField(max_length=255)),
            ],
        ),
        migrations.CreateModel(
            name='Package',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('length', models.DecimalField(decimal_places=3, max_digits=6, verbose_name='Length (inches)')),
                ('width', models.DecimalField(decimal_places=3, max_digits=6, verbose_name='Width (inches)')),
                ('height', models.DecimalField(decimal_places=3, max_digits=6, verbose_name='Height (inches)')),
            ],
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=512)),
                ('image_urls', models.TextField(blank=True, default='')),
            ],
        ),
        migrations.CreateModel(
            name='Warehouse',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=512)),
                ('address_source_id', models.CharField(blank=True, default='', max_length=64)),
                ('address1', models.CharField(max_length=512)),
                ('address2', models.CharField(blank=True, max_length=512)),
                ('company', models.CharField(blank=True, max_length=512)),
                ('city', models.CharField(max_length=512)),
                ('province', models.CharField(blank=True, max_length=512)),
                ('zip', models.CharField(max_length=50)),
                ('country_code', models.CharField(max_length=10)),
                ('country', models.CharField(max_length=255)),
                ('phone', models.CharField(blank=True, max_length=100)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='warehouses',
                                           to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Variant',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=512)),
                ('sku', models.CharField(max_length=512)),
                ('weight', models.DecimalField(decimal_places=3, default=0, max_digits=6, verbose_name='Weight (oz)')),
                ('length', models.DecimalField(decimal_places=3, default=0, max_digits=6,
                                               verbose_name='Length (inches)')),
                ('width', models.DecimalField(decimal_places=3, default=0, max_digits=6,
                                              verbose_name='Width (inches)')),
                ('height', models.DecimalField(decimal_places=3, default=0, max_digits=6,
                                               verbose_name='Height (inches)')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='variants', to='logistics.Product')),
            ],
        ),
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_ids', models.CharField(blank=True, default='', max_length=512)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suppliers',
                                              to='logistics.Product')),
                ('warehouse', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products',
                                                to='logistics.Warehouse')),
            ],
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_data_id', models.CharField(max_length=255)),
                ('listing', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                                              related_name='purchases', to='logistics.Listing')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items',
                                            to='logistics.Order')),
            ],
        ),
        migrations.AddField(
            model_name='order',
            name='package',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='orders', to='logistics.Package'),
        ),
        migrations.AddField(
            model_name='order',
            name='warehouse',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders',
                                    to='logistics.Warehouse'),
        ),
        migrations.AddField(
            model_name='listing',
            name='supplier',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='listings',
                                    to='logistics.Supplier'),
        ),
        migrations.AddField(
            model_name='listing',
            name='variant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suppliers',
                                    to='logistics.Variant'),
        ),
        migrations.CreateModel(
            name='Carrier',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('carrier_type', models.CharField(max_length=512)),
                ('description', models.CharField(max_length=512)),
                ('reference', models.CharField(max_length=512)),
                ('credentials', models.TextField(default='{}')),
                ('source_id', models.CharField(max_length=64)),
                ('account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                              related_name='carriers', to='logistics.Account')),
            ],
        ),
    ]
