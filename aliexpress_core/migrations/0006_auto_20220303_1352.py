# Generated by Django 2.2.27 on 2022-03-03 13:52

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('aliexpress_core', '0005_auto_20220208_1000'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='aliexpresscategory',
            options={'ordering': ['-order'], 'verbose_name_plural': 'Aliexpress Categories'},
        ),
    ]