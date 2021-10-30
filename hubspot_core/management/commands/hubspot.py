from queue import Queue
from threading import Thread
import arrow

from django.contrib.auth.models import User

from hubspot_core.utils import api_requests, clean_plan_name, create_contact, update_contact
from hubspot_core.models import HubspotAccount
from last_seen.models import LastSeen
from leadgalaxy.models import GroupPlan
from shopified_core.commands import DropifiedBaseCommand


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
        parser.add_argument('--missing', action='store_true', help='Add Missing users only')
        parser.add_argument('--skip', action='store', type=int, default=0, help='Skip this number of users')
        parser.add_argument('--threads', action='store', type=int, default=2, help='Number of threads')

    def start_command(self, *args, **options):
        if options['create']:
            self.write('Create Properties...')
            return self.create_properties()

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

            try:
                last_seen = LastSeen.objects.when(user, 'website')
            except KeyboardInterrupt:
                raise
            except:
                last_seen = None

            if last_seen and last_seen > arrow.utcnow().replace(years=-2).datetime:
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
        plans = set([clean_plan_name(i) for i in GroupPlan.objects.all().values_list('title', flat=True)])
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
