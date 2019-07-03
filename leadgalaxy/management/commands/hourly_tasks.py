import datetime

from django.utils import timezone
from django.db.models import Q

from shopified_core.management import DropifiedBaseCommand
from product_feed.models import (
    FeedStatus,
    CommerceHQFeedStatus,
    WooFeedStatus,
    GrooveKartFeedStatus,
)
from product_feed.feed import (
    generate_product_feed,
    generate_chq_product_feed,
    generate_woo_product_feed,
    generate_gkart_product_feed,
)
from leadgalaxy.models import UserProfile, GroupPlan


class Command(DropifiedBaseCommand):

    def start_command(self, *args, **options):
        plan = GroupPlan.objects.get(slug='subuser-plan')
        UserProfile.objects.exclude(subuser_parent=None).exclude(plan=plan).update(plan=plan)

        verbosity = options.get('verbosity', 1)

        self.generate_product_feeds(store_type='shopify', verbosity=verbosity + 1)

        for store_type in ['chq', 'woo', 'gkart']:
            self.generate_product_feeds(store_type=store_type, verbosity=verbosity)

    def get_feed_status_model(self, store_type=''):
        if store_type == 'shopify':
            return FeedStatus
        elif store_type == 'chq':
            return CommerceHQFeedStatus
        elif store_type == 'woo':
            return WooFeedStatus
        elif store_type == 'gkart':
            return GrooveKartFeedStatus

    def get_generate_product_feed(self, store_type=''):
        if store_type == 'shopify':
            return generate_product_feed
        elif store_type == 'chq':
            return generate_chq_product_feed
        elif store_type == 'woo':
            return generate_woo_product_feed
        elif store_type == 'gkart':
            return generate_gkart_product_feed

    def generate_product_feeds(self, store_type='', verbosity=1):
        FeedStatusModel = self.get_feed_status_model(store_type)
        gen_product_feed = self.get_generate_product_feed(store_type)

        an_hour_ago = timezone.now() - datetime.timedelta(hours=1)
        statuses = FeedStatusModel.objects.filter(Q(fb_access_at__gte=an_hour_ago) | Q(google_access_at__gte=an_hour_ago))

        if verbosity >= 1:
            self.stdout.write('Generate {} {} feeds'.format(store_type, len(statuses)))

        for status in statuses:
            if verbosity >= 2:
                self.stdout.write('{} Store Feed: {}'.format(store_type, status.store.shop))
            gen_product_feed(status, nocache=True)
