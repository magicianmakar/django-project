# Generated by Django 3.2.14 on 2022-09-07 17:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0098_alter_usersupplementlabel_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsorderline',
            name='batch_number',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
    ]