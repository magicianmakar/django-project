# Generated by Django 2.2.24 on 2022-01-03 14:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alibaba_core', '0005_auto_20210921_1535'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='alibabaaccount',
            options={'ordering': ['-updated_at']},
        ),
        migrations.AddField(
            model_name='alibabaaccount',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
    ]
