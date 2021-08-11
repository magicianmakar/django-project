# Generated by Django 2.2.24 on 2021-06-29 13:40

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('leadgalaxy', '0225_auto_20210627_2111'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupplan',
            name='parent_plan',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='leadgalaxy.GroupPlan', verbose_name='Use permissions from selected plan'),
        ),
    ]