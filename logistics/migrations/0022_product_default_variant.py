# Generated by Django 3.2.14 on 2022-11-11 17:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0021_merge_0020_auto_20220907_1419_0020_auto_20220908_2359'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='default_variant',
            field=models.BooleanField(blank=True, default=False),
        ),
    ]
