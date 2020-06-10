# Generated by Django 2.2.12 on 2020-06-03 17:34

from django.db import migrations


def forwards_func(apps, schema_editor):
    # We get the model from the versioned app registry;
    # if we directly import it, it'll be the wrong version
    MockupType = apps.get_model('supplements', 'MockupType')
    db_alias = schema_editor.connection.alias

    MockupType.objects.using(db_alias).create(
        slug='4oz-bottle',
        name='4oz. Bottle',
    )
    MockupType.objects.using(db_alias).create(
        slug='colored-container-elderberry',
        name='Elderberry Gummy Container',
    )
    MockupType.objects.using(db_alias).create(
        slug='colored-container-childrens',
        name='Children\'s Gummy Container',
    )
    MockupType.objects.using(db_alias).create(
        slug='colored-container-multi-color',
        name='Multi Color Gummy Container',
    )
    MockupType.objects.using(db_alias).create(
        slug='colored-container-orange',
        name='Orange Gummy Container',
    )
    MockupType.objects.using(db_alias).create(
        slug='colored-container-red',
        name='Red Gummy Container',
    )
    MockupType.objects.using(db_alias).create(
        slug='colored-container-strawberries',
        name='Strawberry Gummy Container',
    )


def reverse_func(apps, schema_editor):
    # forwards_func() creates two Country instances,
    # so reverse_func() should delete them.
    MockupType = apps.get_model('supplements', 'MockupType')
    db_alias = schema_editor.connection.alias

    MockupType.objects.using(db_alias).filter(slug__in=[
        '4oz-bottle',
        'colored-container-elderberry',
        'colored-container-childrens',
        'colored-container-multi-color',
        'colored-container-orange',
        'colored-container-red',
        'colored-container-strawberries',
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('supplements', '0055_usersupplement_label_presets'),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
