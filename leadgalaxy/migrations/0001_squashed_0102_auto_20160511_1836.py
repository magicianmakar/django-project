# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
from django.utils.timezone import utc
import django.db.models.deletion
from django.conf import settings


# Functions from the following migrations have been removed
# as they don't do anything for fresh database migration
# leadgalaxy.migrations.0056_auto_20160130_1230
# leadgalaxy.migrations.0032_auto_20151221_2012
# leadgalaxy.migrations.0038_auto_20151223_1851
# leadgalaxy.migrations.0088_auto_20160314_1347
# leadgalaxy.migrations.0029_auto_20151218_1635
# leadgalaxy.migrations.0048_auto_20160123_1704

class Migration(migrations.Migration):

    replaces = [
        (b'leadgalaxy', '0001_initial'), (b'leadgalaxy', '0002_accesstoken'), (b'leadgalaxy', '0003_shopifyproduct'),
        (b'leadgalaxy', '0004_shopifyproduct_stat'), (b'leadgalaxy', '0005_shopifyproduct_shopify_id'), (b'leadgalaxy', '0006_auto_20151030_2139'),
        (b'leadgalaxy', '0007_shopifyboard'), (b'leadgalaxy', '0008_auto_20151103_1754'), (b'leadgalaxy', '0009_shopifyboard_config'),
        (b'leadgalaxy', '0010_auto_20151124_2042'), (b'leadgalaxy', '0011_shopifyproduct_original_data'), (b'leadgalaxy', '0012_groupplan'),
        (b'leadgalaxy', '0013_userprofile'), (b'leadgalaxy', '0014_userprofile_plan'), (b'leadgalaxy', '0015_remove_groupplan_group'),
        (b'leadgalaxy', '0016_auto_20151130_1731'), (b'leadgalaxy', '0017_auto_20151201_1444'), (b'leadgalaxy', '0018_shopifyproduct_notes'),
        (b'leadgalaxy', '0019_groupplan_default_plan'), (b'leadgalaxy', '0020_userupload'), (b'leadgalaxy', '0021_userupload_url'),
        (b'leadgalaxy', '0022_auto_20151206_1330'), (b'leadgalaxy', '0023_auto_20151212_1344'), (b'leadgalaxy', '0024_auto_20151215_1738'),
        (b'leadgalaxy', '0025_shopifyproductexport'), (b'leadgalaxy', '0026_shopifyproductexport_product'), (b'leadgalaxy', '0027_auto_20151218_1627'),
        (b'leadgalaxy', '0028_shopifyproduct_shopify_export'), (b'leadgalaxy', '0029_auto_20151218_1635'),
        (b'leadgalaxy', '0030_auto_20151218_1717'), (b'leadgalaxy', '0031_shopifyproduct_original_dataz'),
        (b'leadgalaxy', '0032_auto_20151221_2012'), (b'leadgalaxy', '0033_remove_shopifyproduct_original_data'), (b'leadgalaxy', '0034_auto_20151221_2016'),
        (b'leadgalaxy', '0035_shopifyproduct_is_active'), (b'leadgalaxy', '0036_shopifyproduct_parent_product'),
        (b'leadgalaxy', '0037_shopifyproduct_original_json'), (b'leadgalaxy', '0038_auto_20151223_1851'),
        (b'leadgalaxy', '0039_remove_shopifyproduct_original_data'), (b'leadgalaxy', '0040_auto_20151223_1857'), (b'leadgalaxy', '0041_userprofile_config'),
        (b'leadgalaxy', '0042_auto_20160104_1725'), (b'leadgalaxy', '0043_auto_20160104_1730'), (b'leadgalaxy', '0044_shopifyproductimage'),
        (b'leadgalaxy', '0045_shopifyproductimage_image'), (b'leadgalaxy', '0046_shopifyproduct_variants_map'), (b'leadgalaxy', '0047_groupplan_register_hash'),
        (b'leadgalaxy', '0048_auto_20160123_1704'), (b'leadgalaxy', '0049_planregistration'), (b'leadgalaxy', '0050_planregistration_user'),
        (b'leadgalaxy', '0051_shopifyorder'), (b'leadgalaxy', '0052_auto_20160127_1730'), (b'leadgalaxy', '0053_shopifyorder_user'),
        (b'leadgalaxy', '0054_auto_20160129_2042'), (b'leadgalaxy', '0055_shopifyorder_source_id'), (b'leadgalaxy', '0056_auto_20160130_1230'),
        (b'leadgalaxy', '0057_auto_20160130_1509'), (b'leadgalaxy', '0058_shopifyorder_store'), (b'leadgalaxy', '0059_shopifyorder_hidden'),
        (b'leadgalaxy', '0060_shopifywebhook'), (b'leadgalaxy', '0061_shopifywebhook_call_count'), (b'leadgalaxy', '0062_shopifyproduct_price_notification_id'),
        (b'leadgalaxy', '0063_auto_20160217_0041'), (b'leadgalaxy', '0064_aliexpressproductchange'), (b'leadgalaxy', '0065_aliexpressproductchange_user'),
        (b'leadgalaxy', '0066_auto_20160220_1458'), (b'leadgalaxy', '0067_planpayment'), (b'leadgalaxy', '0068_auto_20160222_2145'),
        (b'leadgalaxy', '0069_auto_20160222_2150'), (b'leadgalaxy', '0070_planpayment_transaction_type'), (b'leadgalaxy', '0071_auto_20160222_2229'),
        (b'leadgalaxy', '0072_shopifyorder_seen'), (b'leadgalaxy', '0073_auto_20160226_1924'), (b'leadgalaxy', '0074_auto_20160227_1950'),
        (b'leadgalaxy', '0075_remove_userprofile_full_name'), (b'leadgalaxy', '0076_userprofile_timezone'), (b'leadgalaxy', '0077_userprofile_emails'),
        (b'leadgalaxy', '0078_auto_20160302_1811'), (b'leadgalaxy', '0079_groupplan_slug'), (b'leadgalaxy', '0080_auto_20160305_1427'),
        (b'leadgalaxy', '0081_auto_20160306_1436'), (b'leadgalaxy', '0082_shopifyorder_shopify_status'), (b'leadgalaxy', '0083_auto_20160309_1519'),
        (b'leadgalaxy', '0084_planregistration_email'), (b'leadgalaxy', '0085_auto_20160310_1513'), (b'leadgalaxy', '0086_shopifyorder_auto_fulfilled'),
        (b'leadgalaxy', '0087_shopifystore_store_hash'), (b'leadgalaxy', '0088_auto_20160314_1347'), (b'leadgalaxy', '0089_auto_20160314_1416'),
        (b'leadgalaxy', '0090_auto_20160322_1557'), (b'leadgalaxy', '0091_auto_20160322_1603'), (b'leadgalaxy', '0092_auto_20160331_1254'),
        (b'leadgalaxy', '0093_planregistration_sender'), (b'leadgalaxy', '0094_auto_20160401_1342'), (b'leadgalaxy', '0095_auto_20160401_1527'),
        (b'leadgalaxy', '0096_featurebundle_hidden_from_user'), (b'leadgalaxy', '0097_auto_20160422_1733'), (b'leadgalaxy', '0098_auto_20160425_1459'),
        (b'leadgalaxy', '0099_auto_20160509_1738'), (b'leadgalaxy', '0100_remove_shopifyproduct_stat'), (b'leadgalaxy', '0101_auto_20160509_2241'),
        (b'leadgalaxy', '0102_auto_20160511_1836')
    ]

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auth', '0006_require_contenttypes_0002'),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopifyStore',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(default=b'', max_length=512, blank=True)),
                ('api_url', models.CharField(max_length=512)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='AccessToken',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('token', models.CharField(unique=True, max_length=512)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ShopifyProduct',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('data', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
                ('stat', models.IntegerField(default=0, verbose_name=b'Publish stat')),
                ('shopify_id', models.BigIntegerField(default=0, verbose_name=b'Shopif Product ID')),
            ],
        ),
        migrations.CreateModel(
            name='ShopifyBoard',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(default=b'', max_length=512, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('products', models.ManyToManyField(to=b'leadgalaxy.ShopifyProduct', blank=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
                ('config', models.CharField(default=b'', max_length=512, blank=True)),
            ],
        ),
        migrations.AlterModelOptions(
            name='accesstoken',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterModelOptions(
            name='shopifyboard',
            options={'ordering': ['title']},
        ),
        migrations.AlterModelOptions(
            name='shopifyproduct',
            options={'ordering': ['-created_at']},
        ),
        migrations.AlterModelOptions(
            name='shopifystore',
            options={'ordering': ['-created_at']},
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='original_data',
            field=models.TextField(default=b''),
        ),
        migrations.CreateModel(
            name='GroupPlan',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(default=b'', max_length=512, verbose_name=b'Plan Title', blank=True)),
                ('montly_price', models.FloatField(default=0.0, verbose_name=b'Price Per Month')),
                ('stores', models.IntegerField(default=0)),
                ('products', models.IntegerField(default=0)),
                ('boards', models.IntegerField(default=0)),
                ('badge_image', models.CharField(default=b'', max_length=512, blank=True)),
                ('description', models.CharField(default=b'', max_length=512, blank=True)),
                ('default_plan', models.IntegerField(default=0, choices=[(0, b'No'), (1, b'Yes')])),
            ],
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('status', models.IntegerField(default=1, choices=[(0, b'Pending'), (1, b'Active'), (2, b'Inactive'), (3, b'Hold')])),
                ('full_name', models.CharField(default=b'', max_length=255, blank=True)),
                ('address1', models.CharField(default=b'', max_length=255, blank=True)),
                ('city', models.CharField(default=b'', max_length=255, blank=True)),
                ('state', models.CharField(default=b'', max_length=255, blank=True)),
                ('country', models.CharField(default=b'', max_length=255, blank=True)),
                ('user', models.OneToOneField(related_name='profile', to=settings.AUTH_USER_MODEL)),
                ('plan', models.ForeignKey(to='leadgalaxy.GroupPlan', null=True)),
            ],
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='notes',
            field=models.TextField(default=b''),
        ),
        migrations.CreateModel(
            name='UserUpload',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('product', models.ForeignKey(to='leadgalaxy.ShopifyProduct', null=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
                ('url', models.CharField(default=b'', max_length=512, verbose_name=b'Upload file URL', blank=True)),
            ],
        ),
        migrations.AlterModelOptions(
            name='userupload',
            options={'ordering': ['-created_at']},
        ),
        migrations.AddField(
            model_name='shopifystore',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='AppPermission',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=512, verbose_name=b'Permission')),
                ('description', models.CharField(default=b'', max_length=512, verbose_name=b'Permission Description', blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='groupplan',
            name='permissions',
            field=models.ManyToManyField(to=b'leadgalaxy.AppPermission', blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='notes',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.CreateModel(
            name='ShopifyProductExport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('original_url', models.CharField(default=b'', max_length=512, blank=True)),
                ('shopify_id', models.BigIntegerField(default=0, verbose_name=b'Shopif Product ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submittion date')),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
                ('product', models.ForeignKey(to='leadgalaxy.ShopifyProduct', null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='shopify_export',
            field=models.ForeignKey(to='leadgalaxy.ShopifyProductExport', null=True),
        ),
        migrations.RemoveField(
            model_name='shopifyproduct',
            name='shopify_id',
        ),
        migrations.RemoveField(
            model_name='shopifyproductexport',
            name='product',
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='original_dataz',
            field=models.BinaryField(default=None, null=True),
        ),
        migrations.RemoveField(
            model_name='shopifyproduct',
            name='original_data',
        ),
        migrations.RenameField(
            model_name='shopifyproduct',
            old_name='original_dataz',
            new_name='original_data',
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='parent_product',
            field=models.ForeignKey(verbose_name=b'Dupliacte of product', to='leadgalaxy.ShopifyProduct', null=True),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='original_json',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.RemoveField(
            model_name='shopifyproduct',
            name='original_data',
        ),
        migrations.RenameField(
            model_name='shopifyproduct',
            old_name='original_json',
            new_name='original_data',
        ),
        migrations.AddField(
            model_name='userprofile',
            name='config',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='parent_product',
            field=models.ForeignKey(verbose_name=b'Dupliacte of product', blank=True, to='leadgalaxy.ShopifyProduct', null=True),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='parent_product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Dupliacte of product', blank=True, to='leadgalaxy.ShopifyProduct', null=True),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='shopify_export',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, blank=True, to='leadgalaxy.ShopifyProductExport', null=True),
        ),
        migrations.CreateModel(
            name='ShopifyProductImage',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('product', models.BigIntegerField(verbose_name=b'Shopify Product ID')),
                ('variant', models.BigIntegerField(default=0, verbose_name=b'Shopify Product ID')),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
                ('image', models.CharField(default=b'', max_length=512, blank=True)),
            ],
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='variants_map',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AddField(
            model_name='groupplan',
            name='register_hash',
            field=models.CharField(default=b'', max_length=50, blank=True),
        ),
        migrations.CreateModel(
            name='PlanRegistration',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('register_hash', models.CharField(unique=True, max_length=40)),
                ('data', models.CharField(default=b'', max_length=512, blank=True)),
                ('expired', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('plan', models.ForeignKey(to='leadgalaxy.GroupPlan')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ShopifyOrder',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('order_id', models.BigIntegerField()),
                ('line_id', models.BigIntegerField()),
                ('data', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
                ('source_id', models.BigIntegerField(default=0, verbose_name=b'Source Product ID')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterField(
            model_name='accesstoken',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyboard',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyproductexport',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='shopifyproductexport',
            name='shopify_id',
            field=models.BigIntegerField(default=0, verbose_name=b'Shopify Product ID'),
        ),
        migrations.AlterField(
            model_name='shopifystore',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AlterField(
            model_name='userupload',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date'),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='source_status',
            field=models.CharField(default=b'', max_length=128, verbose_name=b'Source Order Status', blank=True),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='source_tracking',
            field=models.CharField(default=b'', max_length=128, verbose_name=b'Source Tracking Number', blank=True),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='updated_at',
            field=models.DateTimeField(default=datetime.datetime(2016, 1, 30, 15, 9, 33, 428757, tzinfo=utc), verbose_name=b'Last update', auto_now=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='data',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AlterField(
            model_name='shopifyorder',
            name='source_id',
            field=models.BigIntegerField(default=0, verbose_name=b'Source Order ID'),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='store',
            field=models.ForeignKey(to='leadgalaxy.ShopifyStore', null=True),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='ShopifyWebhook',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('topic', models.CharField(max_length=64)),
                ('token', models.CharField(max_length=64)),
                ('shopify_id', models.BigIntegerField(default=0, verbose_name=b'Webhook Shopify ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(to='leadgalaxy.ShopifyStore')),
                ('call_count', models.IntegerField(default=0)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='price_notification_id',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='check_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='status_updated_at',
            field=models.DateTimeField(default=datetime.datetime(2016, 2, 17, 0, 41, 24, 999112, tzinfo=utc), verbose_name=b'Last Status Update', auto_now_add=True),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='AliexpressProductChange',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('hidden', models.BooleanField(default=False, verbose_name=b'Archived change')),
                ('data', models.TextField(default=b'', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name=b'Submission date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name=b'Last update')),
                ('product', models.ForeignKey(to='leadgalaxy.ShopifyProduct')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True)),
                ('seen', models.BooleanField(default=False, verbose_name=b'User viewed the changes')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='PlanPayment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('provider', models.CharField(max_length=50)),
                ('payment_id', models.CharField(max_length=120)),
                ('data', models.TextField(default=b'', blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True)),
                ('email', models.CharField(max_length=120, blank=True)),
                ('fullname', models.CharField(max_length=120, blank=True)),
                ('transaction_type', models.CharField(max_length=32, blank=True)),
            ],
        ),
        migrations.AlterModelOptions(
            name='planpayment',
            options={'ordering': ['-created_at']},
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='seen',
            field=models.BooleanField(default=False, verbose_name=b'User viewed the changes'),
        ),
        migrations.CreateModel(
            name='FeatureBundle',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('title', models.CharField(max_length=30, verbose_name=b'Bundle Title')),
                ('slug', models.SlugField(unique=True, max_length=30, verbose_name=b'Bundle Slug')),
                ('register_hash', models.CharField(unique=True, max_length=50, editable=False)),
                ('description', models.CharField(default=b'', max_length=512, blank=True)),
                ('permissions', models.ManyToManyField(to=b'leadgalaxy.AppPermission', blank=True)),
            ],
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='register_hash',
            field=models.CharField(unique=True, max_length=50),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='bundles',
            field=models.ManyToManyField(to=b'leadgalaxy.FeatureBundle', blank=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='plan_after_expire',
            field=models.ForeignKey(related_name='expire_plan', verbose_name=b'Plan to user after Expire Date', blank=True, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='plan_expire_at',
            field=models.DateTimeField(null=True, verbose_name=b'Plan Expire Date', blank=True),
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='full_name',
        ),
        migrations.AddField(
            model_name='userprofile',
            name='timezone',
            field=models.CharField(default=b'', max_length=255, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='emails',
            field=models.TextField(default=b'', null=True, verbose_name=b'Other Emails', blank=True),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='user',
            field=models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True),
        ),
        migrations.AddField(
            model_name='groupplan',
            name='slug',
            field=models.SlugField(unique=True, max_length=30, verbose_name=b'Plan Slug'),
        ),
        migrations.AlterField(
            model_name='groupplan',
            name='register_hash',
            field=models.CharField(unique=True, max_length=50, editable=False),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='register_hash',
            field=models.CharField(unique=True, max_length=40, editable=False),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='shopify_status',
            field=models.CharField(default=b'', max_length=128, null=True, verbose_name=b'Shopify Fulfillment Status', blank=True),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='data',
            field=models.TextField(default=b'', blank=True),
        ),
        migrations.AddField(
            model_name='planregistration',
            name='email',
            field=models.CharField(default=b'', max_length=120, blank=True),
        ),
        migrations.AddField(
            model_name='planregistration',
            name='bundle',
            field=models.ForeignKey(verbose_name=b'Purchased Bundle', blank=True, to='leadgalaxy.FeatureBundle', null=True),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='plan',
            field=models.ForeignKey(verbose_name=b'Purchased Plan', blank=True, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AddField(
            model_name='shopifyorder',
            name='auto_fulfilled',
            field=models.BooleanField(default=False, verbose_name=b'Automatically fulfilled'),
        ),
        migrations.AddField(
            model_name='shopifystore',
            name='store_hash',
            field=models.CharField(default=b'', max_length=50, null=True, editable=False, blank=True),
        ),
        migrations.AlterField(
            model_name='shopifystore',
            name='store_hash',
            field=models.CharField(default=b'', unique=True, max_length=50, editable=False),
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='address1',
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='city',
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='state',
        ),
        migrations.AddField(
            model_name='userprofile',
            name='boards',
            field=models.IntegerField(default=-2),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='products',
            field=models.IntegerField(default=-2),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='stores',
            field=models.IntegerField(default=-2),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_parent',
            field=models.ForeignKey(related_name='subuser_parent', on_delete=django.db.models.deletion.SET_NULL, blank=True, to=settings.AUTH_USER_MODEL, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='subuser_stores',
            field=models.ManyToManyField(related_name='subuser_stores', to=b'leadgalaxy.ShopifyStore', blank=True),
        ),
        migrations.AddField(
            model_name='planregistration',
            name='sender',
            field=models.ForeignKey(related_name='sender', verbose_name=b'Plan Generated By', blank=True, to=settings.AUTH_USER_MODEL, null=True),
        ),
        migrations.AddField(
            model_name='featurebundle',
            name='hidden_from_user',
            field=models.BooleanField(default=False, verbose_name=b'Hide in User Profile'),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='bundle',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Purchased Bundle', blank=True, to='leadgalaxy.FeatureBundle', null=True),
        ),
        migrations.AlterField(
            model_name='planregistration',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Purchased Plan', blank=True, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='plan_after_expire',
            field=models.ForeignKey(related_name='expire_plan', on_delete=django.db.models.deletion.SET_NULL, verbose_name=b'Plan to user after Expire Date', blank=True, to='leadgalaxy.GroupPlan', null=True),
        ),
        migrations.AlterUniqueTogether(
            name='shopifywebhook',
            unique_together=set([('store', 'topic')]),
        ),
        migrations.AlterField(
            model_name='shopifyproduct',
            name='store',
            field=models.ForeignKey(blank=True, to='leadgalaxy.ShopifyStore', null=True),
        ),
        migrations.RemoveField(
            model_name='shopifyproduct',
            name='stat',
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='price',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='product_type',
            field=models.CharField(default=b'', max_length=255, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='tag',
            field=models.CharField(default=b'', max_length=255, db_index=True, blank=True),
        ),
        migrations.AddField(
            model_name='shopifyproduct',
            name='title',
            field=models.CharField(default=b'', max_length=512, db_index=True, blank=True),
        ),
        migrations.RenameModel(
            old_name='ShopifyOrder',
            new_name='ShopifyOrderTrack',
        ),
    ]
