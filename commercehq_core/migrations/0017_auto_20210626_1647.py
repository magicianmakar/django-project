# Generated by Django 2.2.24 on 2021-06-26 16:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('commercehq_core', '0016_auto_20210626_1413'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commercehqsupplier',
            name='store',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='suppliers', to='commercehq_core.CommerceHQStore'),  # noqa
        ),
    ]
