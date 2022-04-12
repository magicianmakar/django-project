# Generated by Django 2.2.27 on 2022-04-04 19:30

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='InsiderReport',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_of', models.DateField(verbose_name='Report Date')),
                ('report_url', models.URLField(blank=True, default='')),
            ],
        ),
    ]
