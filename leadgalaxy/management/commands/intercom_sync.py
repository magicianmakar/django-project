from django.conf import settings

from shopified_core.commands import DropifiedBaseCommand
from leadgalaxy.models import UserProfile

import arrow
import requests
from lib.exceptions import capture_exception


class Command(DropifiedBaseCommand):
    help = 'Auto fulfill tracked orders with a tracking number and unfulfilled status'

    def add_arguments(self, parser):
        parser.add_argument('--days', action='store', type=int, default=0, help='Sync users updated in last number of days')
        parser.add_argument('--progress', action='store_true', help='Shopw Reset Progress')

    def start_command(self, *args, **options):
        if not settings.INTERCOM_ACCESS_TOKEN:
            self.write('Intercom API key is not set')
            return

        profiles = UserProfile.objects.select_related('user').order_by('updated_at')
        if options['days']:
            profiles = profiles.filter(updated_at__gte=arrow.utcnow().replace(days=-options['days']).datetime) \
                               .exclude(updated_at=None)

        self.progress_total(profiles.count(), enable=options['progress'])

        for profile in profiles:
            try:
                self.update_user(profile)
            except KeyboardInterrupt:
                break
            except:
                capture_exception()

    def update_user(self, profile):
        user = profile.user
        plan = profile.plan

        self.progress_write(f'{user.email} | {profile.plan.title} | {profile.updated_at:%d-%m-%Y}')
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
                'ebay_count': len(profile.get_ebay_stores()),
                'fb_count': len(profile.get_fb_stores()),
                'gkart_count': len(profile.get_gkart_stores()),
                'gear_count': len(profile.get_gear_stores()),
                'bigcommerce_count': len(profile.get_bigcommerce_stores()),
                'addons': ','.join(profile.get_installed_addon_titles())
            }
        }

        data['custom_attributes']['stores_count'] = sum(
            data['custom_attributes'][i] for i in ['shopify_count', 'chq_count', 'woo_count', 'gkart_count', 'gear_count', 'bigcommerce_count', 'ebay_count', 'fb_count']
        )

        try:
            r = requests.post(
                url='https://api.intercom.io/users',
                headers={
                    'Authorization': f'Bearer {settings.INTERCOM_ACCESS_TOKEN}',
                    'Accept': 'application/json'
                },
                json=data)
            r.raise_for_status()
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
            capture_exception(level='warning')
