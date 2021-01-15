# Generated by Django 2.2.16 on 2021-01-15 17:03

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('addons_core', '0016_addonusage_cancel_at'),
        ('leadgalaxy', '0216_groupplan_show_in_plod_app'),
    ]

    operations = [
        migrations.CreateModel(
            name='Offer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(blank=True, default='', max_length=255)),
                ('slug', models.SlugField(blank=True, default='', max_length=255)),
                ('billings', models.ManyToManyField(
                    blank=True,
                    limit_choices_to={'addon__action_url__isnull': True},
                    related_name='offers',
                    to='addons_core.AddonBilling',
                    verbose_name='Addons'
                )),
            ],
        ),
        migrations.CreateModel(
            name='OfferCoupon',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Name will show in customer invoices', max_length=255)),
                ('percent_off', models.DecimalField(decimal_places=2, max_digits=4)),
                ('duration', models.CharField(choices=[('once', 'Once'), ('repeating', 'Repeating'), ('forever', 'Forever')],
                                              default='forever', max_length=20)),
                ('duration_in_months', models.IntegerField(
                    blank=True,
                    default=None,
                    help_text='Required if duration is repeating, specifies the number of months the discount will be in effect',
                    null=True
                )),
                ('redeem_by', models.DateTimeField(
                    blank=True,
                    help_text='Date after which the coupon can no longer be redeemed.',
                    null=True
                )),
                ('stripe_coupon_id', models.CharField(
                    blank=True,
                    default='',
                    help_text='Automatically generated',
                    max_length=255
                )),
            ],
        ),
        migrations.CreateModel(
            name='OfferCustomer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Subscribed date')),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=9)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='offers.Offer')),
                ('seller', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sells', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='offer',
            name='coupon',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='offers.OfferCoupon'),
        ),
        migrations.AddField(
            model_name='offer',
            name='customers',
            field=models.ManyToManyField(related_name='purchases', through='offers.OfferCustomer', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='offer',
            name='owner',
            field=models.ForeignKey(limit_choices_to={'is_staff': True}, on_delete=django.db.models.deletion.PROTECT, related_name='offers',
                                    to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='offer',
            name='plan',
            field=models.ForeignKey(blank=True, limit_choices_to={'payment_gateway': 'stripe', 'payment_interval__in': ['', 'monthly', 'yearly'],
                                                                  'stripe_plan__stripe_id__isnull': False, 'support_addons': True},
                                    null=True,
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='offers', to='leadgalaxy.GroupPlan'),
        ),
    ]
