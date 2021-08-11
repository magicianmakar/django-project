# Generated by Django 2.2.24 on 2021-06-26 12:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gearbubble_core', '0019_gearbubbleproduct_user_supplement'),
    ]

    operations = [
        migrations.AddField(
            model_name='gearbubbleproduct',
            name='bundle_map',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='gearbubbleproduct',
            name='config',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='gearbubbleproduct',
            name='monitor_id',
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name='gearbubbleproduct',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='gearbubbleproduct',
            name='data',
            field=models.TextField(blank=True, default='{}', null=True),
        ),
        migrations.AlterField(
            model_name='gearbubbleproduct',
            name='price',
            field=models.FloatField(default=0.0),
        ),
        migrations.AlterField(
            model_name='gearbubbleproduct',
            name='product_type',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='gearbubbleproduct',
            name='title',
            field=models.TextField(blank=True, db_index=True, null=True),
        ),
    ]