# Generated by Django 2.2.27 on 2022-04-17 20:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0005_auto_20220417_1846'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderitem',
            name='order_track_id',
            field=models.CharField(default='', max_length=255),
            preserve_default=False,
        ),
    ]