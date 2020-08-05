# Generated by Django 2.2.13 on 2020-06-28 17:40

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('addons_core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AddonUsage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('addon', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='addons_core.Addon')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
