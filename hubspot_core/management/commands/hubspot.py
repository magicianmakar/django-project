import json
from collections import defaultdict
from queue import Queue
from threading import Thread

import arrow
import requests

from django.conf import settings
from django.contrib.auth.models import User

from hubspot_core.models import HubspotAccount
from hubspot_core.utils import INTERVALS, api_requests, clean_plan_name, create_contact, update_contact
from last_seen.models import LastSeen
from leadgalaxy.models import GroupPlan, ShopifyStore, UserProfile
from lib.exceptions import capture_exception
from shopified_core.commands import DropifiedBaseCommand
from shopified_core.utils import safe_int, safe_float, safe_str


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
        parser.add_argument('--mrr', action='store_true', help='Get MRR/LTV data')
        parser.add_argument('--missing', action='store_true', help='Add Missing users only')
        parser.add_argument('--skip', action='store', type=int, default=0, help='Skip this number of users')
        parser.add_argument('--threads', action='store', type=int, default=2, help='Number of threads')

    def start_command(self, *args, **options):
        if options['create']:
            self.write('Create Properties...')
            return self.create_properties()

        if options['orders']:
            self.write('Orders data...')
            return self.find_orders()

        if options['mrr']:
            self.write('Get MRR data...')
            return self.find_mrr()

        q = Queue()

        for i in range(options['threads']):
            t = Thread(target=create_contact_worker, args=(self, q))
            t.daemon = True
            t.start()

        users = User.objects.all().order_by('-id')

        skip = options['skip']
        self.progress_total(users.count())
        active_users = []
        for user in users.all():
            self.progress_update()

            if self.is_seen(user):
                if not options['missing'] or not HubspotAccount.objects.filter(hubspot_user=user).exists():
                    active_users.append(user)

        self.progress_close()

        self.progress_total(len(active_users) - skip)
        total_count = 0
        for user in active_users:
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

        self.create_property('dr_orders_7_day_count', 'Orders Count last 7 Days', 'number', 'number')
        self.create_property('dr_orders_14_day_count', 'Orders Count last 14 Days', 'number', 'number')
        self.create_property('dr_orders_30_day_count', 'Orders Count last 30 Days', 'number', 'number')
        self.create_property('dr_orders_90_day_count', 'Orders Count last 90 Days', 'number', 'number')
        self.create_property('dr_orders_120_day_count', 'Orders Count last 120 Days', 'number', 'number')
        self.create_property('dr_orders_365_day_count', 'Orders Count last 365 Days', 'number', 'number')
        self.create_property('dr_orders_all_count', 'Orders Count all time', 'number', 'number')

        self.create_property('dr_orders_7_day_sum', 'Orders Sum last 7 Days', 'number', 'number')
        self.create_property('dr_orders_14_day_sum', 'Orders Sum last 14 Days', 'number', 'number')
        self.create_property('dr_orders_30_day_sum', 'Orders Sum last 30 Days', 'number', 'number')
        self.create_property('dr_orders_90_day_sum', 'Orders Sum last 90 Days', 'number', 'number')
        self.create_property('dr_orders_120_day_sum', 'Orders Sum last 120 Days', 'number', 'number')
        self.create_property('dr_orders_365_day_sum', 'Orders Sum last 365 Days', 'number', 'number')
        self.create_property('dr_orders_all_sum', 'Orders Sum All time', 'number', 'number')

        self.create_property('dr_mrr', 'Users MRR', 'number', 'number')
        self.create_property('dr_ltv', 'Users LTV', 'number', 'number')

        self.update_plan_property_options()

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

    def update_plan_property_options(self):
        plans = set([clean_plan_name(i) for i in GroupPlan.objects.all()])
        options = []
        for plan in plans:
            options.append({
                "label": plan,
                "value": plan,
                "hidden": False
            })

        data = {
            "name": "plan",
            "label": "Plan",
            "type": "enumeration",
            "fieldType": "select",
            "description": "Dropified Plan",
            "groupName": "subscription",
            "formField": True,
            "options": options
        }

        url = 'https://api.hubapi.com/crm/v3/properties/0-1/plan'

        return api_requests(url, data, 'PATCH')

    def find_orders(self):
        filename = 'query_result.csv'
        orders_info = []

        self.write('> Load CSV file')
        with open(filename) as infile:
            for line in infile:
                store_id, created_at, total_sum, count = line.strip().split(',')
                if not safe_int(store_id):
                    continue

                orders_info.append({
                    'store_id': int(store_id),
                    'created_at': arrow.get(created_at),
                    'sum': safe_float(total_sum),
                    'count': safe_int(count),
                })

        orders_info = sorted(orders_info, key=lambda i: i['created_at'], reverse=True)

        def get_default_dates(n):
            return {
                'days': n,
                'week': int(n / 7) if n > 0 else n,
                'orders': 0,
                'sum': 0,
                'count': 0,
            }

        now = arrow.utcnow()

        self.write('> Calc orders info')
        store_orders = {}
        for order in orders_info:
            sid = str(order['store_id'])
            if sid not in store_orders:
                store_orders[sid] = {}
                for t in INTERVALS:
                    store_orders[sid][t] = get_default_dates(int(t))

            for interval in INTERVALS:
                if interval == '-1' or \
                    (now > now.replace(days=-store_orders[sid][interval]['days'])
                        and store_orders[sid][interval]['orders'] < store_orders[sid][interval]['week']):
                    store_orders[sid][interval]['orders'] += 1
                    store_orders[sid][interval]['sum'] += order['sum']
                    store_orders[sid][interval]['count'] += order['count']

        self.write('> Stores map')
        store_user_map = {}
        store_currency_map = {}
        for store in ShopifyStore.objects.all():
            store_user_map[str(store.id)] = str(store.user_id)
            currency = 1.0  # USD
            currency_format = safe_str(store.currency_format).strip()
            if '€' in currency_format or 'EUR' in currency_format:
                currency = 1.14
            elif '£' in currency_format:
                currency = 1.34
            elif 'Rs.' in currency_format:
                currency = 0.013
            elif 'R$' in currency_format:
                currency = 0.18
            elif '₫' in currency_format:
                currency = 0.000044
            elif 'R {{amount}}' == currency_format:
                currency = 0.065
            elif '₱' in currency_format:
                currency = 0.020
            elif 'Tk {{amount}}' in currency_format:
                currency = 0.012
            elif '¥' in currency_format:
                currency = 0.0088
            elif ' sk' in currency_format:
                currency = 0.11
            elif '{{amount}} SR' in currency_format:
                currency = 0.27
            elif 'SFr.' in currency_format:
                currency = 1.09
            elif ' dh' in currency_format or 'dhs' in currency_format:
                currency = 0.11

            store_currency_map[str(store.id)] = currency

        self.write('> Merge users info')
        user_orders_sum = defaultdict(dict)
        user_orders_count = defaultdict(dict)

        for key, val in store_orders.items():
            if key not in store_user_map:
                continue

            sid = store_user_map[key]
            for t in INTERVALS:
                if t not in user_orders_sum[sid]:
                    user_orders_sum[sid][t] = 0.0
                user_orders_sum[sid][t] += val[t]['sum'] * store_currency_map[key]

                if t not in user_orders_count[sid]:
                    user_orders_count[sid][t] = 0
                user_orders_count[sid][t] += val[t]['count']

        self.write(f'user_orders_sum: {len(user_orders_sum)}, user_orders_count: {len(user_orders_count)}')

        self.progress_total(User.objects.count())
        for user in User.objects.all():
            self.progress_update()
            uid = str(user.id)
            if uid in user_orders_sum or uid in user_orders_count:
                user.set_config('_shopify_orders_stat', {
                    'count': user_orders_count[uid],
                    'sum': user_orders_sum[uid]
                })

    def is_seen(self, user):
        try:
            last_seen = LastSeen.objects.when(user, 'website')
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
