# Generated by Django 2.2.24 on 2022-02-08 10:00

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('aliexpress_core', '0004_auto_20220203_0425'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='aliexpresscategory',
            options={'ordering': ['order'], 'verbose_name_plural': 'Aliexpress Categories'},
        ),
    ]
