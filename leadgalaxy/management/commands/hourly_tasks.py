import datetime

from django.db.models import Q
from django.utils import timezone

from leadgalaxy.models import UserProfile, GroupPlan
from metrics.tasks import add_number_metric
from product_feed.feed import (
    generate_product_feed,
    generate_chq_product_feed,
    generate_woo_product_feed,
    generate_gkart_product_feed,
    generate_bigcommerce_product_feed,
)
from product_feed.models import (
    FeedStatus,
    CommerceHQFeedStatus,
    WooFeedStatus,
    GrooveKartFeedStatus,
    BigCommerceFeedStatus,
)
from shopified_core.management import DropifiedBaseCommand
from shopified_core.models_utils import get_store_model


class Command(DropifiedBaseCommand):

    def start_command(self, *args, **options):
        plan = GroupPlan.objects.get(slug='subuser-plan')
        UserProfile.objects.exclude(subuser_parent=None).exclude(plan=plan).update(plan=plan)

        for store_type in ['shopify', 'chq', 'woo', 'gkart', 'bigcommerce']:
            self.generate_product_feeds(store_type=store_type, verbosity=options['verbosity'])
            self.record_metrics(store_type)

    def get_feed_status_model(self, store_type=''):
        if store_type == 'shopify':
            return FeedStatus
        elif store_type == 'chq':
            return CommerceHQFeedStatus
        elif store_type == 'woo':
            return WooFeedStatus
        elif store_type == 'gkart':
            return GrooveKartFeedStatus
        elif store_type == 'bigcommerce':
            return BigCommerceFeedStatus

    def get_generate_product_feed(self, store_type=''):
        if store_type == 'shopify':
            return generate_product_feed
        elif store_type == 'chq':
            return generate_chq_product_feed
        elif store_type == 'woo':
            return generate_woo_product_feed
        elif store_type == 'gkart':
            return generate_gkart_product_feed
        elif store_type == 'bigcommerce':
            return generate_bigcommerce_product_feed

    def generate_product_feeds(self, store_type='', verbosity=1):
        FeedStatusModel = self.get_feed_status_model(store_type)
        gen_product_feed = self.get_generate_product_feed(store_type)

        an_hour_ago = timezone.now() - datetime.timedelta(hours=1)
        statuses = FeedStatusModel.objects.filter(Q(fb_access_at__gte=an_hour_ago) | Q(google_access_at__gte=an_hour_ago))

        if verbosity >= 1:
            self.stdout.write(f'Generate {store_type} {len(statuses)} feeds')

        for status in statuses:
            if verbosity >= 2:
                self.stdout.write(f'{store_type} Store Feed: {status.store.shop}')

            gen_product_feed(status, nocache=True)

    def record_metrics(self, store_type):
        add_number_metric.apply_async(
            args=['stores.active', store_type, get_store_model(store_type).objects.filter(is_active=True).count()],
            expires=500)

        add_number_metric.apply_async(
            args=['stores.inactive', store_type, get_store_model(store_type).objects.filter(is_active=False).count()],
            expires=500)
