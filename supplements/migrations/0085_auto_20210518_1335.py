# Generated by Django 2.2.18 on 2021-05-18 13:35

from django.db import migrations, models


def clean_label_images(apps, schema_editor):
    UserSupplementLabel = apps.get_model('supplements', 'UserSupplementLabel')
    UserSupplementLabel.objects.all().update(image_url=None)


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0084_usersupplementlabel_image_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='plsorderline',
            name='is_bundled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='plsorderline',
            name='order_track_id',
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(clean_label_images),
    ]
