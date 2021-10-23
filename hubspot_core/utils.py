import re
import arrow
import requests
import time

from django.contrib.auth.models import User
from django.conf import settings

from .models import HubspotAccount


def api_requests(url, data, method='post'):
    r = getattr(requests, method.lower())(
        url=url,
        json=data,
        params={'hapikey': settings.HUPSPOT_API_KEY}
    )

    if not r.ok and r.status_code == 429:
        time.sleep(1)
        return api_requests(url=url, data=data, method=method)

    r.raise_for_status()

    return r.json()


def generate_create_contact(user: User):
    profile = user.profile

    try:
        plan = profile.plan
    except:
        plan = None

    try:
        parent_plan = user.models_user.profile.plan
    except:
        parent_plan = None

    data = {
        "properties": {
            "email": user.email,
            "firstname": user.first_name,
            "lastname": user.last_name,
            "phone": profile.phone,
            "country": profile.country,

            "dr_join_date": arrow.get(user.date_joined).timestamp * 1000,
            "dr_plan": plan.title if plan else '',
            "dr_bundles": ','.join(profile.bundles_list()),
            "dr_user_tags": profile.tags,
            "dr_is_subuser": user.is_subuser,
            "dr_parent_plan": parent_plan.title if user.is_subuser else '',
            "dr_payment_gateway": parent_plan.payment_gateway if parent_plan else '',
            "dr_free_plan": parent_plan.free_plan if parent_plan else '',

            "dr_stores_count": 0,
            "dr_shopify_count": profile.get_shopify_stores().count(),
            "dr_chq_count": profile.get_chq_stores().count(),
            "dr_woo_count": profile.get_woo_stores().count(),
            "dr_gear_count": profile.get_gear_stores().count(),
            "dr_gkart_count": profile.get_gkart_stores().count(),
            "dr_bigcommerce_count": profile.get_bigcommerce_stores().count(),
        }
    }

    address = None
    try:
        if profile.company.name:
            address = profile.company
    except:
        pass

    if not address:
        try:
            if profile.address.name:
                address = profile.address
        except:
            pass

    if address:
        data['properties']['dr_company'] = address.name
        data['properties']['dr_state'] = address.state
        data['properties']['dr_country'] = address.country

    data['properties']['dr_stores_count'] = sum([
        data['properties']['dr_shopify_count'],
        data['properties']['dr_chq_count'],
        data['properties']['dr_woo_count'],
        data['properties']['dr_gear_count'],
        data['properties']['dr_gkart_count'],
        data['properties']['dr_bigcommerce_count'],
    ])

    return data


def create_contact(user: User):
    data = generate_create_contact(user)

    try:
        result = api_requests('https://api.hubapi.com/crm/v3/objects/contacts', data, 'POST')

        HubspotAccount.objects.update_or_create(
            hubspot_user=user,
            defaults={
                'hubspot_vid': result['id']
            }
        )

        return result

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 409:
            message = e.response.json().get('message')
            existing_id = re.findall(r'Contact already exists. Existing ID: ([0-9]+)', message)
            if existing_id:
                HubspotAccount.objects.update_or_create(hubspot_user=user, defaults={'hubspot_vid': existing_id.pop()})
                return update_contact(user)

        print('HTTP Error:', user.email, e.response.status_code, re.findall(
            r'\\"message\\":\\"([^\\]+)\\"', e.response.text) or e.response.json().get('message'))
        raise e


def update_contact(user: User):
    try:
        account = HubspotAccount.objects.get(hubspot_user=user)
        data = generate_create_contact(user)
        return api_requests(f'https://api.hubapi.com/crm/v3/objects/contacts/{account.hubspot_vid}', data, 'PATCH')
    except HubspotAccount.DoesNotExist:
        return create_contact(user)
