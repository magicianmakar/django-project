import json
import re
from collections import defaultdict
from queue import Queue
from threading import Thread
from argparse import FileType

import arrow
import requests

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Sum

from hubspot_core.models import HubspotAccount
from hubspot_core.utils import api_requests, create_contact, update_contact, update_plan_property_options
from last_seen.models import LastSeen
from leadgalaxy.models import UserProfile
from lib.exceptions import capture_exception
from shopified_core.commands import DropifiedBaseCommand
from shopify_orders.models import ShopifyOrderRevenue
from suredone_core.utils import SureDoneUtils


def create_contact_worker(cmd, q):
    while True:
        user = q.get()

        try:
            try:
                account = HubspotAccount.objects.get(hubspot_user=user)
                update_contact(user, account=account)
                cmd.write(f'> UPDATE: {user.email}')
            except HubspotAccount.DoesNotExist:
                cmd.write(f'> CREATE: {user.email}')
                create_contact(user)
        except:
            cmd.write(f'> Error for {user.email}')

        cmd.progress_update(1)

        q.task_done()


class Command(DropifiedBaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--create', action='store_true', help='Create Properties only')
        parser.add_argument('--orders', action='store_true', help='Load orders stats')
        parser.add_argument('--get_sd_orders', action='store_true', help='Load sd orders stats')
        parser.add_argument('--tracks', action='store_true', help='Load order tracking info')
        parser.add_argument('--mrr', action='store_true', help='Get MRR/LTV data')
        parser.add_argument('--missing', action='store_true', help='Add Missing users only')
        parser.add_argument('--skip', action='store', type=int, default=0, help='Skip this number of users')
        parser.add_argument('--threads', action='store', type=int, default=2, help='Number of threads')
        parser.add_argument('--admitad', action='append', type=FileType('rb'), help='Admitad file')

    def start_command(self, *args, **options):
        if options['create']:
            self.write('Create Properties...')
            return self.create_properties()

        elif options['orders']:
            self.write('Orders data...')
            return self.find_orders()

        elif options['get_sd_orders']:
            self.write('SD orders data...')
            return self.get_sd_orders()

        elif options['mrr']:
            self.write('Get MRR data...')
            return self.find_mrr()

        elif options['admitad']:
            self.write('Load admitad data')
            return self.load_admitad(options['admitad'])

        elif options['tracks']:
            self.write('Load order tracking data')
            return self.load_tracks()

        q = Queue()

        for i in range(options['threads']):
            t = Thread(target=create_contact_worker, args=(self, q))
            t.daemon = True
            t.start()

        users = User.objects.all().order_by('-id')

        skip = options['skip']
        self.progress_total(users.count())
        active_users = []
        active_users_map = defaultdict(list)
        for user in users.all():
            self.progress_update()

            if self.is_seen(user):
                if not options['missing'] or not HubspotAccount.objects.filter(hubspot_user=user).exists():
                    active_users.append(user)
                    active_users_map[user.email.lower()].append(user)

        unique_active_users = []
        for email, users in active_users_map.items():
            if len(users) == 1:
                unique_active_users.append(users[0])
            else:
                found_user = None
                for u in users:
                    if not u.profile.plan.is_free:
                        found_user = u

                if not found_user:
                    found_user = users[0]

                unique_active_users.append(found_user)

        self.progress_close()

        self.progress_total(len(unique_active_users) - skip)
        total_count = 0
        for user in unique_active_users:
            total_count += 1
            if total_count < skip:
                continue

            q.put(user)

        q.join()

    def import_user(self, user: User):
        create_contact(user)

    def verify(self, user: User):
        return api_requests('https://api.hubspot.com/conversations/v3/visitor-identification/tokens/create', {
            "email": user.email,
            "firstName": user.first_name,
            "lastName": user.last_name
        })

    def create_properties(self):
        self.create_property('dr_join_date', 'Join Date', 'datetime', 'date')
        self.create_property('dr_bundles', 'User Bundles', 'string', 'text')

        self.create_property('dr_user_tags', 'User Tags', 'string', 'text')

        self.create_property('dr_is_subuser', 'Sub User Account', 'enumeration', 'booleancheckbox', is_bool=True)
        self.create_property('dr_parent_plan', 'User Parent Plan', 'string', 'text')
        self.create_property('dr_free_plan', 'Free Plan', 'enumeration', 'booleancheckbox', is_bool=True)

        self.create_property('dr_stores_count', 'All Stores Count', 'number', 'number')
        self.create_property('dr_shopify_count', 'Shopify Store Count', 'number', 'number')
        self.create_property('dr_chq_count', 'CommerceHQ Store Count', 'number', 'number')
        self.create_property('dr_woo_count', 'WooCommerce Store Count', 'number', 'number')
        self.create_property('dr_gear_count', 'GearBubble Store Count', 'number', 'number')
        self.create_property('dr_gkart_count', 'Groovekart Store Count', 'number', 'number')
        self.create_property('dr_bigcommerce_count', 'Bigcommerce Store Count', 'number', 'number')
        self.create_property('dr_ebay_count', 'eBay Store Count', 'number', 'number')
        self.create_property('dr_fb_count', 'Facebook Store Count', 'number', 'number')
        self.create_property('dr_google_count', 'Google Store Count', 'number', 'number')

        self.create_property('dr_tracks_30_day_count', 'Orders Fulfillement last 30 Days', 'number', 'number')
        self.create_property('dr_tracks_all_count', 'Orders Fulfillement all time', 'number', 'number')

        self.create_property('dr_orders_30_day_count', 'Orders Count last 30 Days', 'number', 'number')
        self.create_property('dr_orders_all_count', 'Orders Count all time', 'number', 'number')

        self.create_property('dr_ebay_orders_30_day_count', 'Ebay Orders Count last 30 Days', 'number', 'number')
        self.create_property('dr_ebay_orders_all_count', 'Ebay Orders Count all time', 'number', 'number')

        self.create_property('dr_orders_30_day_sum', 'Orders Sum last 30 Days', 'number', 'number')
        self.create_property('dr_orders_all_sum', 'Orders Sum All time', 'number', 'number')

        self.create_property('dr_mrr', 'Users MRR', 'number', 'number')
        self.create_property('dr_ltv', 'Users LTV', 'number', 'number')

        update_plan_property_options()

    def create_property(self, name, label, ptype, field, is_bool=False):
        self.write(f'> {name}')
        url = 'https://api.hubapi.com/crm/v3/properties/contacts'
        data = {
            "name": name,
            "label": label,
            "type": ptype,
            "fieldType": field,
            "groupName": "dropified",
            "hidden": False,
            "displayOrder": 2,
            "hasUniqueValue": False,
            "formField": True
        }

        if is_bool:
            data['options'] = [
                {
                    "label": "Yes",
                    "description": "User is a subuser",
                    "value": True,
                    "displayOrder": 1,
                    "hidden": False
                },
                {
                    "label": "No",
                    "description": "User is account owner",
                    "value": False,
                    "displayOrder": 2,
                    "hidden": False
                }
            ]

        try:
            return api_requests(url, data, 'POST')
        except:
            self.write(f'Add Property error: {name}')

    def find_orders(self):
        date_limit = arrow.utcnow().replace(days=-30).datetime
        revenues = ShopifyOrderRevenue.objects.filter(created_at__gte=date_limit) \
            .values('user_id').annotate(sum=Sum('total_price_usd')).order_by('-sum')

        self.progress_total(revenues.count())
        for revenue in revenues:
            self.progress_update()
            try:
                user = User.objects.get(id=revenue['user_id'])
                user.set_config('_shopify_orders_revenue', {
                    '30': revenue['sum'],
                })
            except User.DoesNotExist:
                continue

        self.progress_close()

    def get_sd_orders(self):
        date_limit = arrow.utcnow().replace(days=-30)
        platform_type = 'ebay'
        users = User.objects.all().order_by('-id')

        self.progress_total(users.count())

        for user in users:
            self.progress_update()
            stores = user.profile.get_ebay_stores()
            if not stores:
                continue

            sd_utils = SureDoneUtils(user)
            search_filters = ['archived:=0']
            user_sd_orders, total_products_count = sd_utils.get_all_orders(filters=search_filters)
            user_ebay_orders_all = [order for order in user_sd_orders if order.get('channel') == platform_type]
            user_ebay_orders_last_30_days = [order for order in user_ebay_orders_all if arrow.get(order.get('dateutc')) > date_limit]

            user.set_config(f'_{platform_type}_orders_count', {
                '30': len(user_ebay_orders_last_30_days),
                '-1': len(user_ebay_orders_all),
            })

        self.progress_close()

    def is_seen(self, user):
        try:
            last_seen = LastSeen.objects.when(user, 'website')
            if HubspotAccount.objects.filter(hubspot_user=user).exists():
                return True

            return last_seen and last_seen > arrow.utcnow().replace(years=-2).datetime
        except KeyboardInterrupt:
            raise
        except:
            return False

    def find_mrr(self):
        self.load_baremetrics()
        self.write('> Get Shopify Users')

        profiles = UserProfile.objects.filter(shopify_app_store=True).order_by('-id')
        self.progress_total(profiles.count())
        for profile in profiles:
            self.progress_update()
            if self.is_seen(profile.user):
                mrr = 0
                ltv = 0
                for store in profile.get_shopify_stores():
                    try:
                        info = json.loads(store.info)['id']
                    except:
                        self.write(f'> Error: {store.shop}')
                        continue

                    customer = self.get_baremetrics_shopify_customer(info)
                    if customer:
                        mrr += customer['mrr']
                        ltv += customer['ltv']

                profile.user.set_config('_baremetrics_sub', {
                    'mrr': mrr,
                    'ltv': ltv
                })

        self.progress_close()

        self.write('> Get Stripe Users')
        profiles = UserProfile.objects.filter(shopify_app_store=False).order_by('-id')
        self.progress_total(profiles.count())
        for profile in profiles:
            self.progress_update()
            if profile.user.is_stripe_customer() and self.is_seen(profile.user):
                customer = self.get_baremetrics_stripe_customer(profile.user.stripe_customer.customer_id)
                if customer:
                    profile.user.set_config('_baremetrics_sub', {
                        'mrr': customer['mrr'],
                        'ltv': customer['ltv']
                    })

        self.progress_close()

    def get_baremetrics_customer(self, source_id, customer_id):
        return self.bm_data.get(f'{source_id}-{customer_id}')

        if settings.BAREMETRICS_API_KEY:
            try:
                response = requests.get(
                    url=f'https://api.baremetrics.com/v1/{source_id}/customers/{customer_id}',
                    headers={
                        'Authorization': f'Bearer {settings.BAREMETRICS_API_KEY}',
                        'Accept': 'application/json'
                    })

                if response.ok:
                    response.raise_for_status()
                    customer = response.json()['customer']
                    return {
                        'mrr': customer['current_mrr'],
                        'ltv': customer['ltv']
                    }
                else:
                    self.write(f'> Get Customer {customer_id} from {source_id}: {response.status_code} {response.text}')
            except KeyboardInterrupt:
                raise
            except:
                capture_exception()

    def get_baremetrics_shopify_customer(self, shopify_store_id):
        return self.get_baremetrics_customer('68ff6d63-5ed3-4e3a-b5d5-54b43a94026c', f'Shop-{shopify_store_id}')

    def get_baremetrics_stripe_customer(self, customer_id):
        return self.get_baremetrics_customer('3cmEvFZPe5gYI7', customer_id)

    def load_baremetrics(self):
        try:
            self.bm_data = json.load(open('bm_data.json'))
            return
        except:
            self.write('Load Baremetrics data from API...')

        self.bm_data = {}
        headers = {
            'cookie': ''
        }

        self.progress_total(620)
        page = 1
        while True:
            self.progress_update()
            resp = requests.get(
                url=f'https://app.baremetrics.com/api/v2/proxy/customers?per_page=200&page={page}',
                headers=headers
            )

            if not resp.ok:
                self.write('> ERROR:', resp.text)

            page_data = resp.json()

            for c in page_data['customers']:
                self.bm_data[f"{c['source_id']}-{c['oid']}"] = {
                    'mrr': c['current_mrr'],
                    'ltv': c['ltv'],
                }

            if page_data['meta']['pagination']['has_more']:
                page += 1
            else:
                break

        self.progress_close()

        open('bm_data.json', 'wt').write(json.dumps(self.bm_data, indent=2))

    def load_admitad(self, files):
        users = defaultdict(int)
        for f in files:
            for row in self.get_xsl_vlaues(f):
                if row['SubID'] and re.match(r'u[0-9]+$', row['SubID']):
                    users[row['SubID'][1:]] += row['Payment Sum Approved'] + row['Payment Sum Open']

        for user_id, revenue in users.items():
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                continue

            user.set_config('_adm_revene', {
                'sum': revenue
            })

    def get_xsl_vlaues(self, data_file):
        import openpyxl

        wb = openpyxl.load_workbook(filename=data_file, data_only=True)
        ws = wb[list(wb.sheetnames).pop()]
        first_row = True
        column_names = []

        for r in ws.rows:
            row_value = {}
            col_index = 0
            for c in r:
                if first_row:
                    column_names.append(c.value)
                else:
                    row_value[column_names[col_index]] = c.value

                col_index += 1

            if not first_row:
                yield row_value
            else:
                first_row = False

    def load_tracks(self):
        users_maps = defaultdict(dict)

        for timeframe, keyname in {'this_30_days': '30', 'this_36_months': '-1'}.items():
            self.write(f' >> Get orders count for {timeframe}')
            rep = self.get_keen_orders_count(timeframe)
            if rep.ok:
                results = rep.json()['result']
                for result in results:
                    users_maps[result['user_id']][keyname] = result['result']
            else:
                self.write(f'Keen Error: {rep.text}')

        self.progress_total(len(users_maps))
        for user_id, result in users_maps.items():
            self.progress_update()
            try:
                user = User.objects.get(id=user_id)
                user.set_config('_shopify_orders_count', result)
            except User.DoesNotExist:
                continue

        self.progress_close()

    def get_keen_orders_count(self, timeframe):
        return requests.post(
            url=f'https://api.keen.io/3.0/projects/{settings.KEEN_PROJECT_ID}/queries/count',
            headers={'Authorization': settings.KEEN_READ_KEY},
            data={
                "analysis_type": "count",
                "event_collection": "auto_fulfill",
                "timezone": "UTC",
                "group_by": ["user_id"],
                "interval": None,
                "timeframe": timeframe,
                "zero_fill": None,
                "filters": [],
                "order_by": '[{"direction": "DESC", "property_name": "result"}]'
            }
        )
