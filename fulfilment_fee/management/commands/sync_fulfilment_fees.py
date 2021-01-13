from shopified_core.management import DropifiedBaseCommand
from fulfilment_fee.utils import process_sale_transaction_fee
from leadgalaxy.models import ShopifyOrderTrack
from bigcommerce_core.models import BigCommerceOrderTrack
from groovekart_core.models import GrooveKartOrderTrack
from woocommerce_core.models import WooOrderTrack
from commercehq_core.models import CommerceHQOrderTrack
from my_basket.models import BasketOrderTrack
from django.contrib.auth.models import User


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
            help='From date'
        )

        parser.add_argument(
            '-to',
            '--to',
            default=False,
            help='To date'
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
                           CommerceHQOrderTrack,
                           BasketOrderTrack]
            for track_type in track_types:
                tracks = track_type.objects.filter(created_at__gte=options['from'], created_at__lte=options['to'],
                                                   user_id=user.id)
                if options['user_id']:
                    tracks = tracks.filter(user_id=options['user_id'])
                for track in tracks.iterator():
                    res_fee = process_sale_transaction_fee(track)
                    if res_fee:
                        print(f'Processed {res_fee}')
