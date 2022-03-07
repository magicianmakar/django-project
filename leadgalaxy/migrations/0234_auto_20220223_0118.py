# Generated by Django 2.2.26 on 2022-02-23 01:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0233_auto_20211203_1823'),
    ]

    operations = [
        migrations.AlterField(
            model_name='featurebundle',
            name='slug',
            field=models.SlugField(max_length=512, unique=True, verbose_name='Bundle Slug'),
        ),
        migrations.AlterField(
            model_name='featurebundle',
            name='title',
            field=models.CharField(max_length=512, verbose_name='Bundle Title'),
        ),
    ]