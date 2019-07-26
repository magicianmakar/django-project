from django.conf import settings

from shopified_core.management import DropifiedBaseCommand
from leadgalaxy.models import UserProfile

import arrow
import requests
from raven.contrib.django.raven_compat.models import client as raven_client


class Command(DropifiedBaseCommand):
    help = 'Auto fulfill tracked orders with a tracking number and unfulfilled status'

    def add_arguments(self, parser):
        parser.add_argument('--days', action='store', type=int, default=0, help='Sync users updated in last number of days')
        parser.add_argument('--progress', action='store_true', help='Shopw Reset Progress')

    def start_command(self, *args, **options):
        if not settings.INTERCOM_ACCESS_TOKEN:
            self.write('Intercom API key is not set')
            return

        profiles = UserProfile.objects.select_related('user').order_by('-updated_at')
        if options['days']:
            profiles = profiles.filter(updated_at__gte=arrow.utcnow().replace(days=-options['days']).datetime)

        if options['progress']:
            self.progress_total(profiles.count())

        for profile in profiles:
            self.update_user(profile)

    def update_user(self, profile):
        user = profile.user
        plan = profile.plan

        self.write(f'{user.email} | {profile.plan.title} | {profile.updated_at:%d-%m-%Y}')
        self.progress_update(desc=user.email)

        data = {
            "user_id": user.id,
            "email": user.email,
            "custom_attributes": {
                'sub_user': profile.is_subuser,
                'plan': plan.title,
                'free_plan': plan.free_plan,
                'payment_gateway': plan.payment_gateway,
                'shopify_count': len(profile.get_shopify_stores()),
                'chq_count': len(profile.get_chq_stores()),
                'woo_count': len(profile.get_woo_stores()),
                'gkart_count': len(profile.get_gkart_stores()),
                'gear_count': len(profile.get_gear_stores()),
            }
        }

        data['custom_attributes']['stores_count'] = data['custom_attributes']['shopify_count']

        try:
            r = requests.post(
                url='https://api.intercom.io/users',
                headers={
                    'Authorization': f'Bearer {settings.INTERCOM_ACCESS_TOKEN}',
                    'Accept': 'application/json'
                },
                json=data)
            r.raise_for_status()
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
            raven_client.captureException(e)
