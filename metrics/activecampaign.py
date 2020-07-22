import requests
import arrow
from django.conf import settings

from lib.exceptions import capture_message

API_DATE_FORMAT = 'YYYY-MM-DD'
NOT_AVAILABLE = '[Not Available]'
TAGS = dict(
    SHOPIFY_STAFF={'id': 10, 'title': 'Shopify Staff'},
)
CACHED_CUSTOM_FIELDS = {
    'SIGNEDUP_AT': {'id': '18', 'title': 'Signed-up At'},
    'TRIAL_ENDS': {'id': '19', 'title': 'Trial Ends'},
    'STATUS': {'id': '4', 'title': 'Status'},
    'PLAN': {'id': '2', 'title': 'Plan'},
    'PLATFORM': {'id': '3', 'title': 'Platform'},
    'STORES_COUNT': {'id': '6', 'title': 'Stores Count'},
    'SHOPIFY_COUNT': {'id': '7', 'title': 'Shopify Count'},
    'WOOCOMMERCE_COUNT': {'id': '8', 'title': 'WooCommerce Count'},
    'COMMERCEHQ_COUNT': {'id': '9', 'title': 'CommerceHQ Count'},
    'GROOVEKART_COUNT': {'id': '10', 'title': 'GrooveKart Count'},
    'BIGCOMMERCE_COUNT': {'id': '11', 'title': 'BigCommerce Count'},
    'SUB_USER': {'id': '5', 'title': 'Sub User'},
    'DROPIFIED_ID': {'id': '12', 'title': 'Dropified ID'},
    'EXTERNAL_ID': {'id': '13', 'title': 'External ID'},
    'SEND_EMAILS': {'id': '17', 'title': 'Send E-mails'}
}


class Lists:
    CUSTOMERS = 12
    LEADS = 13


def validate_contact(func):
    def wrapper(*args, **kwargs):
        contact_data = func(*args, **kwargs)

        # Staff accounts
        email = contact_data.get('email') or ''
        if 'exitstrategylabs' in email or 'thedevelopmentmachine' in email:
            return {
                'email': email,
                'custom_fields': {
                    'SEND_EMAILS': 'No'
                }
            }

        if 'custom_fields' in contact_data:
            ac_fields = contact_data['custom_fields']

            # For starter and startup
            current_plan = ac_fields.get('PLAN').lower()
            if 'start' in current_plan \
                    or 'free' in current_plan:
                contact_data['custom_fields']['STATUS'] = 'Cancelled'

            send_emails = ac_fields.get('SEND_EMAILS', '').lower()
            if send_emails == 'no':
                contact_data['remove_list_ids'] = f'{Lists.CUSTOMERS},{Lists.LEADS}'

        return contact_data
    return wrapper


class ActiveCampaignAPI:
    _custom_fields = None
    _field_tags = ['PLAN', 'PLATFORM', 'STATUS', 'SUB_USER', 'STORES_COUNT',
                   'SHOPIFY_COUNT', 'WOOCOMMERCE_COUNT', 'COMMERCEHQ_COUNT',
                   'GROOVEKART_COUNT', 'BIGCOMMERCE_COUNT', 'DROPIFIED_ID',
                   'EXTERNAL_ID', 'TRIAL_ENDS', 'SIGNEDUP_AT', 'SEND_EMAILS']

    def __init__(self):
        self.base = f"{settings.ACTIVECAMPAIGN_URL}"
        self.api_url = f"{self.base}/api/3"
        self.headers = {
            'Api-Token': settings.ACTIVECAMPAIGN_KEY
        }

        self.intercom_base = 'https://api.intercom.io'
        self.intercom_headers = {
            'Authorization': f"Bearer {settings.INTERCOM_ACCESS_TOKEN}",
            'Accept': 'application/json'
        }

    def get_url(self, endpoint='', old_version=False):
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"

        if old_version:
            return f"{self.base}{endpoint}"

        return f"{self.api_url}{endpoint}"

    def get_intercom_url(self, endpoint=''):
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"

        return f"{self.intercom_base}{endpoint}"

    @property
    def custom_fields(self):
        if self._custom_fields is None:
            api_url = self.get_url('/fields')
            params = {'limit': 100, 'offset': 0}
            r = requests.get(api_url, headers=self.headers, params=params)

            try:
                r.raise_for_status()
                result = r.json()
            except:
                capture_message(
                    'Retrieve fields for ActiveCampaign',
                    level='warning',
                    extra={
                        'custom_fields_result': r.content,
                        'status_code': r.status_code
                    }
                )
                self._custom_fields = CACHED_CUSTOM_FIELDS
                return self._custom_fields

            self._custom_fields = {}
            count = int(result['meta']['total'])
            offset = 0

            while offset != count:
                if offset > 0:
                    params['offset'] = offset
                    result = requests.get(api_url, headers=self.headers, params=params).json()

                for field in result['fields']:
                    offset += 1
                    if field['perstag'] in self._field_tags:
                        self._custom_fields[field['perstag']] = {
                            'id': field['id'],
                            'title': field['title']
                        }

        return self._custom_fields

    def subscribe_to_list(self, contact_id, list_id=Lists.CUSTOMERS, status=1):
        api_url = self.get_url('/contactLists')

        return requests.post(api_url, headers=self.headers, json={
            "contactList": {
                "list": list_id,
                "contact": contact_id,
                "status": status
            }
        })

    def add_contact_tag(self, contact_id, tag_id):
        api_url = self.get_url('/contactTags')

        return requests.post(api_url, headers=self.headers, json={
            "contactTag": {
                "contact": contact_id,
                "tag": tag_id,
            }
        })

    def update_contact_field(self, contact_id, field_id, value):
        api_url = self.get_url('/fieldValues')
        data = {
            "fieldValue": {
                "contact": contact_id,
                "field": field_id,
                "value": value
            }
        }
        r = requests.post(api_url, headers=self.headers, json=data)
        data = r.json()
        return data

    def update_user_email(self, from_email, to_email):
        if to_email.lower() == from_email.lower():
            return True
        contact = self.get_or_create_contact(from_email)
        api_url = self.get_url(f"/contacts/{contact['id']}")
        r = requests.put(api_url, headers=self.headers, json={
            'contact': {
                'email': to_email
            }
        })
        r.raise_for_status()
        return True

    def get_user_plan_data(self, user):
        trial_ends = ''
        try:
            trial_days_left = user.profile.trial_days_left or 0
        except:
            trial_days_left = 0

        if user.profile.is_subuser:
            status = 'Active'
        elif trial_days_left > 0:
            status = 'Trial'
            trial_ends = arrow.get().replace(days=trial_days_left + 1).format(API_DATE_FORMAT)
        elif user.profile.plan.is_free:
            status = 'Cancelled'
        else:
            status = 'Active'

        return {
            'PLAN': user.profile.plan.title or NOT_AVAILABLE,
            'PLATFORM': user.profile.plan.get_payment_gateway_display() or NOT_AVAILABLE,
            'TRIAL_ENDS': trial_ends,
            'STATUS': status,
        }

    def get_user_store_data(self, user):
        return {
            'SHOPIFY_COUNT': user.profile.get_shopify_stores().count(),
            'WOOCOMMERCE_COUNT': user.profile.get_woo_stores().count(),
            'COMMERCEHQ_COUNT': user.profile.get_chq_stores().count(),
            'GROOVEKART_COUNT': user.profile.get_gkart_stores().count(),
            'BIGCOMMERCE_COUNT': user.profile.get_bigcommerce_stores().count(),
        }

    @validate_contact
    def get_user_data(self, user):
        # Don't count Shopify Employees as contacts
        tags = []
        if user.profile.from_shopify_app_store():
            store = user.profile.get_shopify_stores().first()
            if store and store.get_info['plan_name'] in ['staff', 'staff_business']:
                tags.append(TAGS['SHOPIFY_STAFF']['id'])

        if user.is_staff:
            return {
                'email': user.email,
                'custom_fields': {
                    'SEND_EMAILS': 'No'
                }
            }

        return {
            'email': user.email,
            'firstName': user.first_name,
            'lastName': user.last_name,
            'list_id': Lists.CUSTOMERS,
            'custom_fields': {
                'DROPIFIED_ID': user.id,
                'SUB_USER': user.profile.is_subuser and 'Yes' or 'No',
                'SIGNEDUP_AT': arrow.get(user.date_joined).format(API_DATE_FORMAT),
                **self.get_user_store_data(user),
                **self.get_user_plan_data(user),
            }
        }

    def can_send_intercom_email(self, intercom_contact):
        return not intercom_contact.get('has_hard_bounced') \
            and not intercom_contact.get('marked_email_as_spam') \
            and not intercom_contact.get('unsubscribed_from_emails')

    @validate_contact
    def get_intercom_data(self, intercom_contact):
        full_name = (intercom_contact.get('name') or '').split(' ')
        custom_attributes = intercom_contact.get('custom_attributes') or {}

        # Webhook also uses two contact types: user or contact
        if intercom_contact.get('role') == 'user' or intercom_contact.get('type') == 'user':
            list_id = Lists.CUSTOMERS
            dropified_id = intercom_contact.get('external_id', intercom_contact.get('user_id'))
            external_id = ''
        else:
            list_id = Lists.LEADS
            dropified_id = NOT_AVAILABLE
            external_id = intercom_contact.get('external_id')

        plan = custom_attributes.get('plan') or ''
        payment_gateway = custom_attributes.get('payment_gateway') or ''
        if 'shopify' in plan.lower() or payment_gateway == 'shopify':
            payment_gateway = 'Shopify'
        else:
            payment_gateway = {
                'stripe': 'Stripe',
                'jvzoo': 'JVZoo'
            }.get(payment_gateway, '')

        signed_up_at = intercom_contact.get('signed_up_at')
        signed_up_since = 15
        if signed_up_at:  # Attempt to identify user on trial
            signed_up_at = arrow.get(signed_up_at)
            signed_up_since = (arrow.get() - signed_up_at).days
            signed_up_at = arrow.get(signed_up_at).format(API_DATE_FORMAT)

        status = ''
        trial_ends = ''
        stripe_status = custom_attributes.get('stripe_subscription_status', '')
        if signed_up_since < 15 and list_id != Lists.LEADS or stripe_status == 'trialing':
            status = 'Trial'
            trial_ends = arrow.get().replace(days=16 - signed_up_since).format(API_DATE_FORMAT)
        elif stripe_status == 'active':
            status = 'Active'
        elif stripe_status == 'canceled':
            status = 'Cancelled'
            if 'black' in plan.lower():  # Issue with 3 months payment
                status = 'Active'

        return {
            'email': intercom_contact.get('email'),
            'firstName': full_name[0],
            'lastName': ' '.join(full_name[1:]),
            'phone': intercom_contact.get('phone'),
            'list_id': list_id,
            'custom_fields': {
                'DROPIFIED_ID': dropified_id,
                'EXTERNAL_ID': external_id,
                'SHOPIFY_COUNT': custom_attributes.get('shopify_count') or '0',
                'WOOCOMMERCE_COUNT': custom_attributes.get('woo_count') or '0',
                'COMMERCEHQ_COUNT': custom_attributes.get('chq_count') or '0',
                'GROOVEKART_COUNT': custom_attributes.get('gkart_count') or '0',
                'BIGCOMMERCE_COUNT': custom_attributes.get('bigcommerce_count') or '0',
                'PLAN': plan,
                'PLATFORM': payment_gateway,
                'TRIAL_ENDS': trial_ends,
                'STATUS': status,
                'SIGNEDUP_AT': signed_up_at,
                'SUB_USER': custom_attributes.get('sub_user') and 'Yes' or 'No',
                'SEND_EMAILS': self.can_send_intercom_email(intercom_contact) and 'Yes' or 'No',
            }
        }

    def update_customer(self, contact_data, version='1'):
        if not contact_data.get('email'):
            return False

        # First version updates in single API call
        if version == '1':
            data = {
                'api_key': settings.ACTIVECAMPAIGN_KEY,
                'api_action': 'contact_sync',
                'api_output': 'json',
                'email': contact_data['email'],
            }

            if contact_data.get('firstName'):
                data['first_name'] = contact_data['firstName']
                data['last_name'] = contact_data['lastName']
                if contact_data.get('phone'):
                    data['phone'] = contact_data['phone']

            if contact_data.get('list_id'):
                data[f"p[{contact_data['list_id']}]"] = str(contact_data['list_id'])
                data[f"status[{contact_data['list_id']}]"] = '1'

            if contact_data.get('remove_list_ids'):
                remove_list_ids = contact_data.get('remove_list_ids', '').split(',')
                for remove_list_id in remove_list_ids:
                    data[f"p[{remove_list_id}]"] = str(remove_list_id)
                    data[f"status[{remove_list_id}]"] = '2'

            if contact_data.get('tags'):
                tags_to_string = {v['id']: v['title'] for k, v in TAGS.items()}
                data['tags'] = ','.join([tags_to_string[t] for t in contact_data.get('tags')])

            for key, value in contact_data.get('custom_fields', {}).items():
                field_id = self.custom_fields.get(key, {}).get('id')
                if not field_id:
                    continue

                data[f'field[%{key}%,0]'] = value

            url = self.get_url('/admin/api.php', old_version=True)
            r = requests.post(url, data=data)
            result = r.json()
            assert result.get('result_code') == 1, f"{contact_data['email']} Contact not updated"
        else:
            data = {}
            if contact_data.get('firstName'):
                data['firstName'] = contact_data['firstName']
                data['lastName'] = contact_data['lastName']
                if contact_data.get('phone'):
                    data['phone'] = contact_data['phone']

            contact = self.get_or_create_contact(contact_data['email'], data)

            if contact_data.get('list_id'):
                self.subscribe_to_list(contact['id'], list_id=contact_data['list_id'])

            if contact_data.get('remove_list_ids'):
                remove_list_ids = contact_data.get('remove_list_ids', '').split(',')
                for remove_list_id in remove_list_ids:
                    self.subscribe_to_list(contact['id'],
                                           list_id=remove_list_id,
                                           status=2)

            for tag_id in contact_data.get('tags', []):
                self.add_contact_tag(contact['id'], tag_id)

            for key, value in contact_data.get('custom_fields', {}).items():
                field_id = self.custom_fields.get(key, {}).get('id')
                if not field_id:
                    continue

                self.update_contact_field(contact['id'], field_id, value)

    def get_contacts_missing_info(self):
        api_url = self.get_url('/admin/api.php', old_version=True)
        r = requests.get(api_url, params={
            'filters[fields][%PLAN%]': NOT_AVAILABLE,
            'filters[fields][%STATUS%]': NOT_AVAILABLE,
            'api_key': settings.ACTIVECAMPAIGN_KEY,
            'api_action': 'contact_list',
            'api_output': 'json'
        })
        # Returns dict with numbers as string instead of list
        result = r.json()
        # Last 3 items are {result_code, result_message, result_output}
        data = list(result.values())[:-3]
        return data

    def check_user_exists(self, user):
        api_url = self.get_url('/contacts')
        r = requests.get(api_url, headers=self.headers, params={
            'email': user.email
        })
        r.raise_for_status()
        result = r.json()

        # Needs dropified ID
        if len(result['contacts']) > 0:
            contact_id = result['contacts'][0]['id']
            api_url = self.get_url(f"/contacts/{contact_id}/fieldValues")
            r = requests.get(api_url, headers=self.headers)
            result = r.json()

            dropified_id_field = self.custom_fields['DROPIFIED_ID']['id']
            for field_value in result['fieldValues']:
                if field_value['field'] == dropified_id_field and field_value['value']:
                    return field_value['value'] not in ['-', NOT_AVAILABLE]

        return False

    def get_or_create_contact(self, email, contact_info=None):
        """
        :param contact_info: non-required dict with {firstName, lastName, phone}
        """
        contact_info = contact_info or {}
        api_url = self.get_url('/contact/sync')
        r = requests.post(api_url, headers=self.headers, json={
            "contact": {
                **contact_info,
                "email": email,
            }
        })

        data = r.json()['contact']
        return data

    def search_intercom_by(self, **kwargs):
        if not kwargs:
            return []

        field = list(kwargs.keys())[0]
        return requests.post(
            self.get_intercom_url('/contacts/search'),
            headers=self.intercom_headers,
            json={'query': {
                'field': field,
                'operator': '=',
                'value': kwargs[field]
            }}
        )
