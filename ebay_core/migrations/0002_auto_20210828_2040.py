# Generated by Django 2.2.24 on 2021-08-28 20:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ebay_core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ebaystore',
            name='auth_token_exp_date',
            field=models.DateTimeField(default=None, verbose_name='Store authorization token expiration date'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='ebaystore',
            name='store_instance_id',
            field=models.IntegerField(db_index=True, default=None, editable=False, verbose_name="Store's instance ID"),
            preserve_default=False,
        ),
    ]