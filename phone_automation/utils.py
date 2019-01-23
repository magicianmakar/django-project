import re
import dateutil.parser
from datetime import datetime

from django.utils import timezone
from django.db.models import Sum
from django.conf import settings
from django.urls import reverse

import requests
from twilio.rest import Client
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core.utils import app_link


CHQ_ORDER_STATUSES = {
    0: 'Not sent to fulfilment',
    1: 'Partially sent to fulfilment',
    2: 'Partially sent to fulfilment and shipped',
    3: 'Sent to fulfilment',
    4: 'Partially shipped',
    5: 'Shipped',
}
CHQ_ORDER_PAID = {
    '0': 'Not paid',
    '1': 'Paid',
    '-1': 'Partially refunded',
    '-2': 'Fully refunded',
}


def get_month_totals(user):
    date_start = timezone.now().replace(day=1)
    month_total_duration = user.twilio_logs.filter(
        log_type='status-callback'
    ).order_by('-created_at').filter(
        created_at__gte=date_start
    ).aggregate(Sum('call_duration'))

    return month_total_duration['call_duration__sum']


def get_month_limit(user):
    if user.can('phone_automation_unlimited_calls.use'):
        limit = False
    else:
        limit = int(settings.PHONE_AUTOMATION_MONTH_LIMIT)
    return limit


def get_twilio_client():
    return Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)


# helper function for get order by customer's phone number
def get_orders_by_phone(user, phone, phone_raw):

    shopify_filter_status = 'open'  # - to get only open orders
    # shopify_filter_status = 'any'  # - to get all orders (debugging)
    orders = {'shopify': [], 'woo': [], 'chq': [], 'gear': []}
    shopify_stores = user.profile.get_shopify_stores()
    woo_stores = user.profile.get_woo_stores()
    chq_stores = user.profile.get_chq_stores()
    gear_stores = user.profile.get_gear_stores()

    # - trick - formatting phone in popular formats to allow more search results for unsupported store types
    phone_dashed = str(phone_format(phone_raw))
    phone_all_formats = [phone_raw, phone, phone_dashed]
    phone_all_formats = list(set(phone_all_formats))

    for shopify_store in shopify_stores:
        try:
            resp_customers = requests.get(url=shopify_store.get_link('/admin/customers/search.json', api=True),
                                          params={'query': 'phone:' + phone,
                                                  'fields': 'id'})
            resp_customers.raise_for_status()
            for shopify_customer in resp_customers.json()['customers']:
                resp_customer_orders = requests.get(
                    url=shopify_store.get_link('/admin/customers/' + str(shopify_customer['id']) + '/orders.json',
                                               api=True), params={'status': shopify_filter_status})
                resp_customer_orders.raise_for_status()
                for shopify_order in resp_customer_orders.json()['orders']:
                    orders['shopify'].append(shopify_order)
        except:
            raven_client.captureException()

    for woo_store in woo_stores:
        try:
            for phone_woo in phone_all_formats:
                resp_customer_orders = woo_store.wcapi.get("orders?search=" + phone_woo + "&status=processing")
                resp_customer_orders.raise_for_status()
                for woo_order in resp_customer_orders.json():
                    if woo_order not in orders['woo']:
                        orders['woo'].append(woo_order)

                # another status processing
                resp_customer_orders = woo_store.wcapi.get("orders?search=" + phone_woo + "&status=pending")
                resp_customer_orders.raise_for_status()
                for woo_order in resp_customer_orders.json():
                    if woo_order not in orders['woo']:
                        orders['woo'].append(woo_order)

        except:
            raven_client.captureException()

    for chq_store in chq_stores:
        try:
            url = chq_store.get_api_url('customers', 'search')
            chq_customers = []
            for phone_chq in phone_all_formats:
                resp_customers = chq_store.request.post(url=url, json={"address": {"phone": phone_chq},
                                                                       "fields": "id"})
                resp_customers.raise_for_status()
                for chq_customer in resp_customers.json()['items']:
                    if chq_customer not in chq_customers:
                        chq_customers.append(chq_customer)
                        resp_customer_orders = chq_store.request.post(chq_store.get_api_url('orders', 'search'),
                                                                      json={"customer_id": chq_customer['id'],
                                                                            "status": [0, 1, 2, 3, 4],
                                                                            "fields": "order_date,id,display_number,status,paid,updated_at,total"})  #
                        resp_customer_orders.raise_for_status()
                        for chq_order in resp_customer_orders.json()['items']:
                            if chq_order not in orders['chq']:
                                orders['chq'].append(chq_order)
        except:
            raven_client.captureException()

    for gear_store in gear_stores:
        try:
            resp_customer_orders = gear_store.request.get(gear_store.get_api_url('private_orders'),
                                                          params={"limit": "50",
                                                                  "fulfillment_status": "unshipped",
                                                                  "fields": "updated_at,id,status,shipped,fulfilled,"
                                                                            "updated_at,amount"})

            resp_customer_orders.raise_for_status()

            resp_customer_orders.raise_for_status()
            for gear_order in resp_customer_orders.json()['orders']:
                if re.sub(r"\D", "", str(gear_order['phone_number'])) == phone:
                    if gear_order not in orders['gear']:
                        orders['gear'].append(gear_order)
        except:
            raven_client.captureException()

    return orders


def phone_format(phone_number):
    clean_phone_number = re.sub(r'[^0-9]+', '', phone_number)
    formatted_phone_number = re.sub(r"(\d)(?=(\d{3})+(?!\d))", r"\1-", "%d" % int(clean_phone_number[:-1])) +\
        clean_phone_number[-1]
    return formatted_phone_number


# helper function for get order by order id value
def get_orders_by_id(user, order_id):

    shopify_filter_status = 'any'  # - to get only open orders
    orders = {'shopify': [], 'woo': [], 'chq': [], 'gear': []}
    shopify_stores = user.profile.get_shopify_stores()
    woo_stores = user.profile.get_woo_stores()
    chq_stores = user.profile.get_chq_stores()
    gear_stores = user.profile.get_gear_stores()

    for shopify_store in shopify_stores:
        try:
            resp_customer_orders = requests.get(
                url=shopify_store.get_link('/admin/orders.json',
                                           api=True), params={'ids': order_id, 'status': shopify_filter_status})
            resp_customer_orders.raise_for_status()
            for shopify_order in resp_customer_orders.json()['orders']:
                orders['shopify'].append(shopify_order)
        except:
            raven_client.captureException()

    for woo_store in woo_stores:
        try:
            resp_customer_orders = woo_store.wcapi.get("orders?include=" + order_id + "")
            resp_customer_orders.raise_for_status()
            for woo_order in resp_customer_orders.json():
                orders['woo'].append(woo_order)
        except:
            raven_client.captureException()

    for chq_store in chq_stores:
        try:
            resp_customer_orders = chq_store.request.post(chq_store.get_api_url('orders', 'search'),
                                                          json={"id": order_id})
            resp_customer_orders.raise_for_status()
            for chq_order in resp_customer_orders.json()['items']:
                orders['chq'].append(chq_order)

            resp_customer_orders = chq_store.request.post(chq_store.get_api_url('orders', 'search'),
                                                          json={"display_number": order_id})
            resp_customer_orders.raise_for_status()
            for chq_order in resp_customer_orders.json()['items']:
                if chq_order not in orders['chq']:
                    orders['chq'].append(chq_order)

        except:
            raven_client.captureException()

    for gear_store in gear_stores:
        try:
            resp_customer_orders = gear_store.request.get(gear_store.get_api_url('private_orders'),
                                                          params={"limit": "50",
                                                          "ids": order_id})

            resp_customer_orders.raise_for_status()

            resp_customer_orders.raise_for_status()
            for gear_order in resp_customer_orders.json()['orders']:
                orders['gear'].append(gear_order)
        except:
            raven_client.captureException()

    return orders


def get_sms_text(orders):
    message = ""

    for order in orders['shopify']:
        updated_at = dateutil.parser.parse(order['processed_at']).strftime("%Y-%m-%d %H:%M:%S")
        message += '\nOrder #' + str(order['id']) + ' (Shopify Order #:' + str(
            order['order_number']) + ' ) : ' + str(order['financial_status']) + ', ' +\
            str(order['fulfillment_status']) + ' ' + str(updated_at) + '; Total: $' + str(order['total_price']) + ''

    for order in orders['woo']:
        updated_at = dateutil.parser.parse(order['date_modified']).strftime("%Y-%m-%d %H:%M:%S")
        message += '\nOrder #' + str(order['id']) + ' ( WooCommerce #:' + str(
            order['number']) + ' ) : ' + str(order['status']) + ', ' + \
            ('unfulfilled' if order['date_completed'] is None else 'fulfilled') + ' ' \
            + str(updated_at) + '; Total: $' + str(order['total']) + ''

    for order in orders['chq']:
        updated_at = datetime.utcfromtimestamp(order['order_date']).strftime("%Y-%m-%d %H:%M:%S")
        message += '\nOrder #' + str(order['id']) + ' ( CHQ #:' + str(order['display_number']) + \
                   ' ) : ' + \
            str(CHQ_ORDER_STATUSES[order['status']]) + ', ' + str(CHQ_ORDER_PAID[str(order['paid'])]) + ' ' +\
            str(updated_at) + '; Total: $' + str(order['total']) + ''

    for order in orders['gear']:
        updated_at = dateutil.parser.parse(order['updated_at']).strftime("%Y-%m-%d %H:%M:%S")
        message += '\nOrder #' + str(order['id']) + ' ( GB #:' + str(order['id']) + \
                   ' ) : ' + \
            str(order['status']) + ', ' + ('unfulfilled' if order['shipped'] is False else 'fulfilled') + ' ' +\
            str(updated_at) + '; Total: $' + str(order['amount']) + ''

    return message


def check_sms_abilities(phone):
    client = get_twilio_client()

    if phone.twilio_metadata['capabilities']['sms'] is True and phone.twilio_metadata['sms_url'] == "":
        # activating sms webhook
        client \
            .incoming_phone_numbers(phone.twilio_sid) \
            .update(sms_url=app_link(reverse('phone_automation_sms_flow')))

        phone.twilio_metadata['sms_url'] = app_link(reverse('phone_automation_sms_flow'))
        phone.save()

    if phone.twilio_metadata['sms_url'] != "":
        return True
    else:
        return False
