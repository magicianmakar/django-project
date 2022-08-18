import re
import arrow
import requests
import time

from django.contrib.auth.models import User
from django.conf import settings
from leadgalaxy.models import GroupPlan

from shopified_core.utils import safe_int, safe_str
from .models import HubspotAccount


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


def update_contact(user: User, account: HubspotAccount = None):
    try:
        if account is None:
            account = HubspotAccount.objects.get(hubspot_user=user)

        data = generate_create_contact(user)
        return api_requests(f'https://api.hubapi.com/crm/v3/objects/contacts/{account.hubspot_vid}', data, 'PATCH')
    except HubspotAccount.DoesNotExist:
        return create_contact(user)


def clean_plan_name(plan):
    if plan.hubspot_title:
        return plan.hubspot_title

    plan = plan.title
    plan = plan.replace('Plan', '').replace('Yearly', '').replace('Monthly', '').replace('Shopify', '')
    plan = re.sub(r'Shopify$', '', plan).strip()
    plan = re.sub(r'[0-9]+ Days Trial', '', plan).strip()
    plan = re.sub(r'\(\$[0-9]+\)', '', plan).strip()
    if plan.strip() != 'Free':
        plan = re.sub(r'Free$', '', plan).strip()
    plan = re.sub(r'RT$', '', plan).strip()
    plan = re.sub(r'Stripe$', '', plan).strip()
    plan = re.sub(r'(Webinar)', '', plan).strip()
    plan = re.sub(r'60DC', '', plan).strip()
    plan = re.sub(r'VIP', '', plan).strip()
    plan = re.sub(r'Beta', '', plan).strip()
    plan = re.sub(r'Special Offer', '', plan).strip()
    plan = re.sub(r'One Time', '', plan).strip()
    plan = re.sub(r'Free Access', '', plan).strip()
    plan = re.sub(r'\(Pro', '', plan).strip()
    plan = re.sub(r'[0-9]+ Pay(ments)?', '', plan).strip()
    plan = re.sub(r'[0-9]+ Year', '', plan).strip()
    plan = plan.strip(' -()')
    plan = re.sub(r'Shopify$', '', plan).strip()
    plan = re.sub(r'Trial$', '', plan).strip()
    plan = re.sub(r'For Lifetime', '', plan).strip()
    plan = re.sub(r'Free Gift', '', plan).strip()

    return plan


def api_requests(url, data, method='post'):
    r = getattr(requests, method.lower())(
        url=url,
        json=data,
        params={'hapikey': settings.HUPSPOT_API_KEY}
    )

    if not r.ok:
        if r.status_code == 429:
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
            "firstname": safe_str(user.first_name).replace('.', ' '),
            "lastname": safe_str(user.last_name).replace('.', ' '),
            "phone": profile.phone,
            "country": profile.country,

            "dr_join_date": arrow.get(user.date_joined).timestamp * 1000,
            "dr_bundles": ','.join(profile.bundles_list()),
            "dr_user_tags": profile.tags,
            "dr_is_subuser": user.is_subuser,
            "dr_parent_plan": clean_plan_name(parent_plan) if user.is_subuser else '',
            "dr_free_plan": parent_plan.free_plan if parent_plan else '',

            "dr_stores_count": 0,
            "dr_shopify_count": profile.get_shopify_stores().count(),
            "dr_chq_count": profile.get_chq_stores().count(),
            "dr_woo_count": profile.get_woo_stores().count(),
            "dr_gear_count": profile.get_gear_stores().count(),
            "dr_gkart_count": profile.get_gkart_stores().count(),
            "dr_bigcommerce_count": profile.get_bigcommerce_stores().count(),
            "dr_ebay_count": profile.get_ebay_stores().count(),
            "dr_fb_count": profile.get_fb_stores().count(),
            "dr_google_count": profile.get_google_stores().count(),

            "plan": clean_plan_name(plan) if plan else '',
            "billing_interval": plan.payment_interval if plan else '',
            "install_source": parent_plan.payment_gateway if parent_plan else '',
            "user_level": 'Sub User' if user.is_subuser else 'User',
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
        data['properties']['company'] = address.name
        data['properties']['city'] = address.state
        data['properties']['state'] = address.state
        data['properties']['country'] = address.country

    data['properties']['dr_stores_count'] = sum([
        data['properties']['dr_shopify_count'],
        data['properties']['dr_chq_count'],
        data['properties']['dr_woo_count'],
        data['properties']['dr_gear_count'],
        data['properties']['dr_gkart_count'],
        data['properties']['dr_bigcommerce_count'],
        data['properties']['dr_ebay_count'],
        data['properties']['dr_fb_count'],
        data['properties']['dr_google_count'],
    ])

    data['properties']['number_of_stores'] = data['properties']['dr_stores_count']

    data['properties']['dr_tracks_all_count'] = 0
    data['properties']['dr_tracks_30_day_count'] = 0

    data['properties']['dr_orders_all_count'] = 0
    data['properties']['dr_orders_30_day_count'] = 0

    data['properties']['dr_orders_30_day_sum'] = 0
    data['properties']['dr_orders_all_sum'] = 0

    data['properties']['dr_ebay_orders_all_count'] = 0
    data['properties']['dr_ebay_orders_30_day_count'] = 0

    shopify_orders_count = user.get_config('_shopify_orders_count')
    if shopify_orders_count:
        for stat_info_name in ['30', '-1']:
            name = f'{stat_info_name}_day' if stat_info_name != '-1' else 'all'
            if shopify_orders_count.get(stat_info_name):
                data['properties'][f'dr_tracks_{name}_count'] = int(shopify_orders_count[stat_info_name])

    shopify_orders_revenue = user.get_config('_shopify_orders_revenue')
    if shopify_orders_revenue:
        for stat_info_name in ['30']:
            if shopify_orders_revenue.get(stat_info_name):
                data['properties'][f'dr_orders_{stat_info_name}_day_sum'] = int(shopify_orders_revenue[stat_info_name])

    shopify_orders_stat = user.get_config('_shopify_orders_stat')
    if shopify_orders_stat:
        for inter in ['30', '-1']:
            name = f'{inter}_day' if inter != '-1' else 'all'
            for stat_info_name in ['count']:
                if shopify_orders_stat.get(stat_info_name):
                    data['properties'][f'dr_orders_{name}_{stat_info_name}'] = int(shopify_orders_stat[stat_info_name][inter])

    ebay_orders_count = user.get_config('_ebay_orders_count')
    if ebay_orders_count:
        for stat_info_name in ['30', '-1']:
            name = f'{stat_info_name}_day' if stat_info_name != '-1' else 'all'
            if ebay_orders_count.get(stat_info_name):
                data['properties'][f'dr_ebay_orders_{name}_count'] = int(ebay_orders_count[stat_info_name])

    baremetrics_sub_stat = user.get_config('_baremetrics_sub')
    if baremetrics_sub_stat:
        data['properties']['dr_mrr'] = safe_int(baremetrics_sub_stat['mrr'] / 100)
        data['properties']['dr_ltv'] = safe_int(baremetrics_sub_stat['ltv'] / 100)

    admitad_revenue = user.get_config('_adm_revene')
    if admitad_revenue:
        data['properties']['store_revenue'] = admitad_revenue['sum']

    return data


def update_plan_property_options():
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
