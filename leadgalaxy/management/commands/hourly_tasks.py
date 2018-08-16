import datetime

from django.utils import timezone

from shopified_core.management import DropifiedBaseCommand
from product_feed.models import FeedStatus, CommerceHQFeedStatus
from product_feed.feed import generate_product_feed, generate_chq_product_feed
from leadgalaxy.models import UserProfile, GroupPlan


class Command(DropifiedBaseCommand):

    def start_command(self, *args, **options):
        plan = GroupPlan.objects.get(slug='subuser-plan')
        UserProfile.objects.exclude(subuser_parent=None).exclude(plan=plan).update(plan=plan)

        self.generate_product_feeds()
        self.generate_chq_product_feeds()

    def generate_product_feeds(self):
        an_hour_ago = timezone.now() - datetime.timedelta(hours=1)
        statuses = FeedStatus.objects.filter(fb_access_at__gte=an_hour_ago)

        self.stdout.write('Generate {} feeds'.format(len(statuses)))

        for status in statuses:
            self.stdout.write(u'Store Feed: {}'.format(status.store.shop))
            generate_product_feed(status, nocache=True)

    def generate_chq_product_feeds(self):
        an_hour_ago = timezone.now() - datetime.timedelta(hours=1)
        chq_statuses = CommerceHQFeedStatus.objects.filter(fb_access_at__gte=an_hour_ago)

        self.stdout.write('Generate CHQ {} feeds'.format(len(chq_statuses)))

        for chq_status in chq_statuses:
            generate_chq_product_feed(chq_status, nocache=True)
