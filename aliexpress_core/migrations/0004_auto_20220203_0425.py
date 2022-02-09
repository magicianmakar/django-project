# Generated by Django 2.2.24 on 2022-02-03 04:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('aliexpress_core', '0003_aliexpresscategory'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='aliexpresscategory',
            options={'ordering': ['order']},
        ),
        migrations.AddField(
            model_name='aliexpresscategory',
            name='description',
            field=models.CharField(blank=True, default='', max_length=512, verbose_name='Name visible to users'),
        ),
        migrations.AddField(
            model_name='aliexpresscategory',
            name='is_hidden',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='aliexpresscategory',
            name='order',
            field=models.IntegerField(blank=True, null=True, verbose_name='Sort Order'),
        ),
        migrations.AddField(
            model_name='aliexpresscategory',
            name='slug',
            field=models.SlugField(default='', max_length=255),
            preserve_default=False,
        ),
    ]
