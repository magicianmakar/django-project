from django.contrib.auth.models import User
import dateutil.parser
from django.utils.timezone import make_aware
from bigcommerce_core.models import BigCommerceOrderTrack
from commercehq_core.models import CommerceHQOrderTrack
from ebay_core.models import EbayOrderTrack
from facebook_core.models import FBOrderTrack
from google_core.models import GoogleOrderTrack
from fulfilment_fee.utils import process_sale_transaction_fee
from groovekart_core.models import GrooveKartOrderTrack
from leadgalaxy.models import ShopifyOrderTrack
from my_basket.models import BasketOrderTrack
from shopified_core.commands import DropifiedBaseCommand
from woocommerce_core.models import WooOrderTrack


class Command(DropifiedBaseCommand):
    help = 'Sync unprocessed Sales Fees pre date range'

    def add_arguments(self, parser):
        parser.add_argument(
            '-u_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

        parser.add_argument(
            '-from',
            '--from',
            default=False,
            help='From date (%Y-%m-%d)'
        )

        parser.add_argument(
            '-to',
            '--to',
            default=False,
            help='To date (%Y-%m-%d)'
        )

    def start_command(self, *args, **options):

        users = User.objects.filter(profile__plan__permissions__name='sales_fee.use')

        if options['user_id']:
            users = User.objects.filter(pk=options['user_id'])

        for user in users.iterator():
            track_types = [ShopifyOrderTrack,
                           BigCommerceOrderTrack,
                           GrooveKartOrderTrack,
                           WooOrderTrack,
                           EbayOrderTrack,
                           FBOrderTrack,
                           GoogleOrderTrack,
                           CommerceHQOrderTrack,
                           BasketOrderTrack]
            for track_type in track_types:
                tracks = track_type.objects.filter(created_at__gte=make_aware(dateutil.parser.parse(options['from'])),
                                                   created_at__lte=make_aware(dateutil.parser.parse(options['to'])),
                                                   user_id=user.id)
                if options['user_id']:
                    tracks = tracks.filter(user_id=options['user_id'])
                for track in tracks.iterator():
                    res_fee = process_sale_transaction_fee(track)
                    if res_fee:
                        print(f'Processed {res_fee}')
