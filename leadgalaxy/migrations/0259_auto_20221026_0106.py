# Generated by Django 3.2.14 on 2022-10-26 01:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0258_auto_20221026_0101'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppPermissionTag',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128)),
                ('slug', models.CharField(max_length=64, unique=True)),
                ('description', models.TextField(blank=True, default='')),
            ],
        ),
        migrations.RemoveField(
            model_name='apppermission',
            name='tags',
        ),
        migrations.AddField(
            model_name='apppermission',
            name='tags',
            field=models.ManyToManyField(blank=True, to='leadgalaxy.AppPermissionTag'),
        ),
    ]
