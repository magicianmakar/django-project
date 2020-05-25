# Generated by Django 2.2.12 on 2020-05-13 11:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('phone_automation', '0007_auto_20200115_1500'),
    ]

    operations = [
        migrations.AlterField(
            model_name='twiliophonenumber',
            name='status',
            field=models.CharField(choices=[('active', 'Incoming calls allowed'), ('inactive', 'Forwardning all incoming calls'), ('released', 'Released'), ('scheduled_deletion', 'Scheduled for deletion')], default='', max_length=50),
        ),
    ]