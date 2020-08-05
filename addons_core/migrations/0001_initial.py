# Generated by Django 2.2.12 on 2020-06-04 15:04

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('leadgalaxy', '0204_auto_20200518_1906'),
    ]

    operations = [
        migrations.CreateModel(
            name='Addon',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.TextField()),
                ('slug', models.SlugField(max_length=512, unique=True)),
                ('addon_hash', models.TextField(editable=False, unique=True)),
                ('short_description', models.TextField()),
                ('description', models.TextField()),
                ('icon_url', models.TextField(blank=True, null=True)),
                ('monthly_price', models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True, verbose_name='Monthly Price(in USD)')),
                ('hidden', models.BooleanField(default=False, verbose_name='Hidden from users')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('permissions', models.ManyToManyField(blank=True, to='leadgalaxy.AppPermission')),
            ],
        ),
    ]
