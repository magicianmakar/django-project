# Generated by Django 2.2.24 on 2021-07-12 21:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('article', '0030_auto_20200219_2233'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='candu_slug',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='article',
            name='show_breadcrumb',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='article',
            name='show_searchbar',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='article',
            name='show_sidebar',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='article',
            name='show_header',
            field=models.BooleanField(default=True, verbose_name='Show Page Title'),
        ),
    ]