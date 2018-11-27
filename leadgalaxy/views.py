# -*- coding: utf-8 -*-
import StringIO
import base64
import hmac
import mimetypes
import random
import time
import traceback
import urllib
import zlib
from hashlib import sha1
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth import logout as user_logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache, caches
from django.core.mail import send_mail
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.core.signing import Signer
from django.db import transaction
from django.db.models import Count, Max, F, Q
from django.http import JsonResponse, HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404, render_to_response, redirect
from django.template import RequestContext
from django.template.defaultfilters import truncatewords
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from raven.contrib.django.raven_compat.models import client as raven_client

from analytic_events.models import RegistrationEvent

from shopified_core import permissions
from shopified_core.paginators import SimplePaginator, FakePaginator
from shopified_core.shipping_helper import get_counrties_list, country_from_code, aliexpress_country_code_map
from shopified_core.mixins import ApiResponseMixin
from shopified_core.exceptions import ApiLoginException
from shopify_orders import utils as shopify_orders_utils
from commercehq_core.models import CommerceHQProduct
from product_alerts.models import ProductChange
from stripe_subscription.stripe_api import stripe

from shopified_core.utils import (
    ALIEXPRESS_REJECTED_STATUS,
    app_link,
    send_email_from_template,
    version_compare,
    order_data_cache,
    update_product_data_images,
    encode_params,
    decode_params,
)

from shopify_orders.models import (
    ShopifyOrder,
    ShopifySyncStatus,
    ShopifyOrderShippingLine,
    ShopifyOrderVariant,
    ShopifyOrderLog,
)
from stripe_subscription.utils import (
    process_webhook_event,
    sync_subscription,
    get_stripe_invoice,
    get_stripe_invoice_list,
)

from product_alerts.utils import variant_index

from profit_dashboard.models import FacebookAccess

import tasks
import utils
from .forms import *
from .models import *
from .templatetags.template_helper import money_format


@login_required
def index_view(request):
    user = request.user

    stores = user.profile.get_shopify_stores()
    config = user.models_user.profile.get_config()

    first_visit = config.get('_first_visit', True)

    if first_visit:
        user.set_config('_first_visit', False)

    if user.profile.plan.slug == 'jvzoo-free-gift':
        first_visit = False

    can_add, total_allowed, user_count = permissions.can_add_store(user)

    extra_stores = can_add and user.profile.plan.is_stripe() and \
        user.profile.get_stores_count() >= total_allowed and \
        total_allowed != -1

    add_store_btn = not user.is_subuser \
        and (can_add or user.profile.plan.extra_stores) \
        and not user.profile.from_shopify_app_store()

    pending_sub = user.shopifysubscription_set.filter(status='pending')
    if len(pending_sub):
        charge = pending_sub[0].refresh()
        if charge.status == 'pending':
            request.session['active_subscription'] = charge.id
            return HttpResponseRedirect(charge.confirmation_url)

    templates = DescriptionTemplate.objects.filter(user=user.models_user).defer('description')
    markup_rules = PriceMarkupRule.objects.filter(user=user.models_user)

    return render(request, 'index.html', {
        'stores': stores,
        'config': config,
        'first_visit': first_visit or request.GET.get('new'),
        'extra_stores': extra_stores,
        'add_store_btn': add_store_btn,
        'templates': templates,
        'markup_rules': markup_rules,
        'page': 'index',
        'user_statistics': cache.get('user_statistics_{}'.format(user.id)),
        'breadcrumbs': ['Stores']
    })


def webhook(request, provider, option):
    if provider == 'paylio' and request.method == 'POST':
        if option not in ['vip-elite', 'elite', 'pro', 'basic']:
            return JsonResponse({'error': 'Unknown Plan'}, status=404)

        plan_map = {
            'vip-elite': '64543a8eb189bae7f9abc580cfc00f76',
            'elite': '3eccff4f178db4b85ff7245373102aec',
            'pro': '55cb8a0ddbc9dacab8d99ac7ecaae00b',
            'basic': '2877056b74f4683ee0cf9724b128e27b',
            'free': '606bd8eb8cb148c28c4c022a43f0432d'
        }

        plan = GroupPlan.objects.get(register_hash=plan_map[option])

        if 'payer_email' not in request.POST:
            return HttpResponse('ok')

        try:
            status = request.POST['status']
            if status not in ['new', 'canceled', 'refunded']:
                raise Exception('Unknown Order status: {}'.format(status))

            data = {
                'email': request.POST['payer_email'],
                'status': status,
                'lastname': request.POST['payer_lastname'],
                'firstname': request.POST['payer_firstname'],
                'payer_id': request.POST['payer_id'],
            }
        except Exception:
            raven_client.captureException()

            send_mail(subject='Dropified: Webhook exception',
                      recipient_list=['chase@dropified.com', 'ma7dev@gmail.com'],
                      from_email=settings.DEFAULT_FROM_EMAIL,
                      message='EXCEPTION: {}\nGET:\n{}\nPOST:\n{}\nMETA:\n{}'.format(
                              traceback.format_exc(),
                              utils.format_data(dict(request.GET.iteritems()), False),
                              utils.format_data(dict(request.POST.iteritems()), False),
                              utils.format_data(request.META, False)))

            raise Http404('Error during proccess')

        if status == 'new':
            reg = utils.generate_plan_registration(plan, data)
            data['reg_hash'] = reg.register_hash
            data['plan_title'] = plan.title

            send_email_from_template(
                tpl='webhook_register.html',
                subject='Your Dropified Access',
                recipient=data['email'],
                data=data,
            )

            utils.slack_invite(data)

            send_mail(subject='Dropified: New Registration',
                      recipient_list=['chase@dropified.com'],
                      from_email=settings.DEFAULT_FROM_EMAIL,
                      message='A new registration link was generated and send to a new user.\n\nMore information:\n{}'.format(
                          utils.format_data(data)))

            return HttpResponse('ok')
        elif status in ['canceled', 'refunded']:
            try:
                user = User.objects.get(email__iexact=data['email'])

                free_plan = GroupPlan.objects.get(register_hash=plan_map['free'])
                user.profile.plan = free_plan
                user.profile.save()

                data['previous_plan'] = plan.title
                data['new_plan'] = free_plan.title

                send_mail(subject='Dropified: Cancel/Refund',
                          recipient_list=['chase@dropified.com'],
                          from_email=settings.DEFAULT_FROM_EMAIL,
                          message='A Dropified User has canceled his/her subscription.\n\nMore information:\n{}'.format(
                              utils.format_data(data)))

                return HttpResponse('ok')

            except Exception:
                raven_client.captureException()

                send_mail(subject='Dropified: Webhook Cancel/Refund exception',
                          recipient_list=['chase@dropified.com', 'ma7dev@gmail.com'],
                          from_email=settings.DEFAULT_FROM_EMAIL,
                          message='EXCEPTION: {}\nGET:\n{}\nPOST:\n{}\nMETA:\n{}'.format(
                              traceback.format_exc(),
                              utils.format_data(dict(request.GET.iteritems()), False),
                              utils.format_data(dict(request.POST.iteritems()), False),
                              utils.format_data(request.META, False)))

                raise Http404('Error during proccess')

    elif provider == 'jvzoo':
        try:
            if ':' not in option and option not in ['vip-elite', 'elite', 'pro', 'basic']:
                return JsonResponse({'error': 'Unknown Plan'}, status=404)

            plan_map = {
                'vip-elite': '64543a8eb189bae7f9abc580cfc00f76',
                'elite': '3eccff4f178db4b85ff7245373102aec',
                'pro': '55cb8a0ddbc9dacab8d99ac7ecaae00b',
                'basic': '2877056b74f4683ee0cf9724b128e27b',
                'free': '606bd8eb8cb148c28c4c022a43f0432d'
            }

            plan = None
            bundle = None

            if ':' in option:
                option_type, option_title = option.split(':')
                if option_type == 'bundle':
                    bundle = FeatureBundle.objects.get(slug=option_title)
                elif option_type == 'plan':
                    plan = GroupPlan.objects.get(slug=option_title)
            else:
                # Before bundles, option is the plan slug
                plan = GroupPlan.objects.get(register_hash=plan_map[option])

            if request.method == 'GET':
                webhook_type = 'Plan'
                if bundle:
                    webhook_type = 'Bundle'

                if not request.user.is_superuser:
                    return JsonResponse({'status': 'ok'})
                else:
                    return HttpResponse('<i>JVZoo</i> Webhook for <b><span style=color:green>{}</span>: {}</b>'
                                        .format(webhook_type, (bundle.title if bundle else plan.title)))

            elif request.method != 'POST':
                raise Exception('Unexpected HTTP Method: {}'.request.method)

            params = dict(request.POST.iteritems())

            # verify and parse post
            utils.jvzoo_verify_post(params)
            data = utils.jvzoo_parse_post(params)

            trans_type = data['trans_type']
            if trans_type not in ['SALE', 'BILL', 'RFND', 'CANCEL-REBILL', 'CGBK', 'INSF']:
                raise Exception('Unknown Transaction Type: {}'.format(trans_type))

            if trans_type == 'SALE':
                if plan:
                    data['jvzoo'] = params

                    expire = request.GET.get('expire')
                    if expire:
                        if expire != '1y':
                            raven_client.captureMessage('Unsupported Expire format',
                                                        extra={'expire': expire})

                        expire_date = timezone.now() + timezone.timedelta(days=365)
                        data['expire_date'] = expire_date.isoformat()
                        data['expire_param'] = expire

                    reg = utils.generate_plan_registration(plan, data)

                    data['reg_hash'] = reg.register_hash
                    data['plan_title'] = plan.title

                    try:
                        user = User.objects.get(email__iexact=data['email'])
                        print 'WARNING: JVZOO SALE UPGARDING: {} to {}'.format(data['email'], plan.title)
                    except User.DoesNotExist:
                        user = None
                    except Exception:
                        raven_client.captureException()
                        user = None

                    if user:
                        user.profile.apply_registration(reg)
                    else:
                        send_email_from_template(
                            tpl='webhook_register.html',
                            subject='Your Dropified Access',
                            recipient=data['email'],
                            data=data)

                else:
                    # Handle bundle purchase
                    data['bundle_title'] = bundle.title

                    data['jvzoo'] = params
                    reg = utils.generate_plan_registration(plan=None, bundle=bundle, data=data)

                    try:
                        user = User.objects.get(email__iexact=data['email'])
                        user.profile.apply_registration(reg)
                    except User.DoesNotExist:
                        user = None

                    send_email_from_template(
                        tpl='webhook_bundle_purchase.html',
                        subject='[Dropified] You Have Been Upgraded To {}'.format(bundle.title),
                        recipient=data['email'],
                        data=data)

                data.update(params)

                tasks.invite_user_to_slack.delay(slack_teams=request.GET.get('slack', 'users'), data=data)

                smartmemeber = request.GET.get('sm')
                if smartmemeber:
                    tasks.smartmemeber_webhook_call.delay(subdomain=smartmemeber, data=params)

                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

                tags = {'trans_type': trans_type}
                if plan:
                    tags['sale_type'] = 'Plan'
                    tags['sale_title'] = plan.title
                else:
                    tags['sale_type'] = 'Bundle'
                    tags['sale_title'] = bundle.title

                raven_client.captureMessage('JVZoo New Purchase',
                                            extra={'name': data['fullname'], 'email': data['email'],
                                                   'trans_type': trans_type, 'payment': payment.id},
                                            tags=tags,
                                            level='info')

                return JsonResponse({'status': 'ok'})

            elif trans_type == 'BILL':
                data['jvzoo'] = params
                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

            elif trans_type in ['RFND', 'CANCEL-REBILL', 'CGBK', 'INSF']:
                try:
                    user = User.objects.get(email__iexact=data['email'])
                except User.DoesNotExist:
                    user = None

                new_refund = PlanPayment.objects.filter(payment_id=params['ctransreceipt'],
                                                        transaction_type=trans_type).count() == 0

                if new_refund:
                    if user:
                        if plan:
                            free_plan = GroupPlan.objects.get(register_hash=plan_map['free'])
                            user.profile.plan = free_plan
                            user.profile.save()

                            data['previous_plan'] = plan.title
                            data['new_plan'] = free_plan.title
                        elif bundle:
                            data['removed_bundle'] = bundle.title
                            user.profile.bundles.remove(bundle)
                    else:
                        PlanRegistration.objects.filter(plan=plan, bundle=bundle, email__iexact=data['email']) \
                                                .update(expired=True)

                data['new_refund'] = new_refund
                data['jvzoo'] = params

                payment = PlanPayment(fullname=data['fullname'],
                                      email=data['email'],
                                      user=user,
                                      provider='JVZoo',
                                      transaction_type=trans_type,
                                      payment_id=params['ctransreceipt'],
                                      data=json.dumps(data))
                payment.save()

                if new_refund:
                    raven_client.captureMessage('JVZoo User Cancel/Refund',
                                                extra={'name': data['fullname'], 'email': data['email'],
                                                       'trans_type': trans_type, 'payment': payment.id},
                                                tags={'trans_type': trans_type},
                                                level='info')

                return JsonResponse({'status': 'ok'})

        except Exception:
            raven_client.captureException()
            return JsonResponse({'error': 'Server Error'}, status=500)

        return JsonResponse({'status': 'ok', 'warning': 'Unknown'})

    elif provider == 'zaxaa':
        if ':' not in option and option not in ['vip-elite', 'elite', 'pro', 'basic']:
            return JsonResponse({'error': 'Unknown Plan'}, status=404)

        plan_map = {
            'vip-elite': '64543a8eb189bae7f9abc580cfc00f76',
            'elite': '3eccff4f178db4b85ff7245373102aec',
            'pro': '55cb8a0ddbc9dacab8d99ac7ecaae00b',
            'basic': '2877056b74f4683ee0cf9724b128e27b',
            'free': '606bd8eb8cb148c28c4c022a43f0432d'
        }

        plan = None
        bundle = None

        if ':' in option:
            option_type, option_title = option.split(':')
            if option_type == 'bundle':
                bundle = FeatureBundle.objects.get(slug=option_title)
            elif option_type == 'plan':
                plan = GroupPlan.objects.get(slug=option_title)
        else:
            # Before bundles, option is the plan slug
            plan = GroupPlan.objects.get(register_hash=plan_map[option])

        if request.method == 'GET':
            webhook_type = 'Plan'
            if bundle:
                webhook_type = 'Bundle'

            if not request.user.is_superuser:
                return JsonResponse({'status': 'ok'})
            else:
                return HttpResponse('<i>JVZoo</i> Webhook for <b><span style=color:green>{}</span>: {}</b>'
                                    .format(webhook_type, (bundle.title if bundle else plan.title)))

        elif request.method != 'POST':
            raise Exception('Unexpected HTTP Method: {}'.request.method)

        params = dict(request.POST.iteritems())

        # verify and parse request
        utils.zaxaa_verify_post(params)
        data = utils.zaxaa_parse_post(params)

        trans_type = data['trans_type']
        if trans_type not in ['SALE', 'FIRST_BILL', 'REBILL', 'CANCELED', 'REFUND']:
            raise Exception('Unknown Transaction Type: {}'.format(trans_type))

        if trans_type in ['SALE', 'FIRST_BILL']:
            if plan:
                data['zaxaa'] = params

                expire = request.GET.get('expire')
                if expire:
                    if expire != '1y':
                        raven_client.captureMessage('Unsupported Expire format',
                                                    extra={'expire': expire})

                    expire_date = timezone.now() + timezone.timedelta(days=365)
                    data['expire_date'] = expire_date.isoformat()
                    data['expire_param'] = expire

                reg = utils.generate_plan_registration(plan, data)

                data['reg_hash'] = reg.register_hash
                data['plan_title'] = plan.title

                try:
                    user = User.objects.get(email__iexact=data['email'])
                    print 'WARNING: ZAXAA SALE UPGARDING: {} to {}'.format(data['email'], plan.title)
                except User.DoesNotExist:
                    user = None
                except Exception:
                    raven_client.captureException()
                    user = None

                if user:
                    user.profile.apply_registration(reg)
                else:
                    send_email_from_template(
                        tpl='webhook_register.html',
                        subject='Your Dropified Access',
                        recipient=data['email'],
                        data=data)

            else:
                # Handle bundle purchase
                data['bundle_title'] = bundle.title

                data['zaxaa'] = params
                reg = utils.generate_plan_registration(plan=None, bundle=bundle, data=data)

                try:
                    user = User.objects.get(email__iexact=data['email'])
                    user.profile.apply_registration(reg)
                except User.DoesNotExist:
                    user = None

                send_email_from_template(
                    tpl='webhook_bundle_purchase.html',
                    subject='[Dropified] You Have Been Upgraded To {}'.format(bundle.title),
                    recipient=data['email'],
                    data=data)

            data.update(params)

            tasks.invite_user_to_slack.delay(slack_teams=request.GET.get('slack', 'users'), data=data)

            smartmemeber = request.GET.get('sm')
            if smartmemeber:
                tasks.smartmemeber_webhook_call.delay(subdomain=smartmemeber, data=params)

            payment = PlanPayment(fullname=data['fullname'],
                                  email=data['email'],
                                  provider='Zaxaa',
                                  transaction_type=trans_type,
                                  payment_id=params['trans_receipt'],
                                  data=json.dumps(data))
            payment.save()

            tags = {'trans_type': trans_type}
            if plan:
                tags['sale_type'] = 'Plan'
                tags['sale_title'] = plan.title
            else:
                tags['sale_type'] = 'Bundle'
                tags['sale_title'] = bundle.title

            raven_client.captureMessage('Zaxaa New Purchase',
                                        extra={'name': data['fullname'], 'email': data['email'],
                                               'trans_type': trans_type, 'payment': payment.id},
                                        tags=tags,
                                        level='info')

            return JsonResponse({'status': 'ok'})

        elif trans_type == 'REBILL':
            data['zaxaa'] = params
            payment = PlanPayment(fullname=data['fullname'],
                                  email=data['email'],
                                  provider='Zaxaa',
                                  transaction_type=trans_type,
                                  payment_id=params['trans_receipt'],
                                  data=json.dumps(data))
            payment.save()

        elif trans_type in ['CANCELED', 'REFUND']:
            try:
                user = User.objects.get(email__iexact=data['email'])
            except User.DoesNotExist:
                user = None

            new_refund = PlanPayment.objects.filter(payment_id=params['trans_receipt'],
                                                    transaction_type=trans_type).count() == 0

            new_refund = True  # Disable this check until we see Zaxaa behavior

            if new_refund:
                if user:
                    if plan:
                        free_plan = GroupPlan.objects.get(register_hash=plan_map['free'])
                        user.profile.plan = free_plan
                        user.profile.save()

                        data['previous_plan'] = plan.title
                        data['new_plan'] = free_plan.title
                    elif bundle:
                        data['removed_bundle'] = bundle.title
                        user.profile.bundles.remove(bundle)
                else:
                    PlanRegistration.objects.filter(plan=plan, bundle=bundle, email__iexact=data['email']) \
                                            .update(expired=True)

            data['new_refund'] = new_refund
            data['zaxaa'] = params

            payment = PlanPayment(fullname=data['fullname'],
                                  email=data['email'],
                                  user=user,
                                  provider='Zaxaa',
                                  transaction_type=trans_type,
                                  payment_id=params['trans_receipt'],
                                  data=json.dumps(data))
            payment.save()

            if new_refund:
                raven_client.captureMessage('Zaxaa User Cancel/Refund',
                                            extra={'name': data['fullname'], 'email': data['email'],
                                                   'trans_type': trans_type, 'payment': payment.id},
                                            tags={'trans_type': trans_type},
                                            level='info')

        return HttpResponse('ok')

    elif provider == 'shopify' and request.method == 'POST':
        try:
            token = request.GET['t']
            topic = option.replace('-', '/')
            try:
                store = ShopifyStore.objects.get(id=request.GET['store'], is_active=True)
            except ShopifyStore.DoesNotExist:
                return HttpResponse('ok')

            if token != utils.webhook_token(store.id):
                raise Exception('Unvalide token: {} <> {}'.format(
                    token, utils.webhook_token(store.id)))

            if 'products' in topic:
                # Shopify send a JSON POST request
                shopify_product = json.loads(request.body)
                product = None
                try:
                    product = ShopifyProduct.objects.get(
                        store=store,
                        shopify_id=shopify_product['id'])
                except:
                    return JsonResponse({'status': 'ok', 'warning': 'Processing exception'})

            elif 'orders' in topic:
                shopify_order = json.loads(request.body)
                cache.set('saved_orders_clear_{}'.format(store.id), True, timeout=300)
            elif 'shop' in topic or 'app' in topic:
                shop_data = json.loads(request.body)
            else:
                raven_client.captureMessage('Non-handled Shopify Topic',
                                            extra={'topic': topic, 'store': store})

                return JsonResponse({'status': 'ok', 'warning': 'Non-handled Topic'})

            if topic == 'products/update':
                cache.set('webhook_product_{}_{}'.format(store.id, shopify_product['id']), shopify_product, timeout=600)

                countdown_key = 'eta_product_{}_{}'.format(store.id, shopify_product['id'])
                if cache.get(countdown_key) is None:
                    cache.set(countdown_key, True, timeout=5)
                    tasks.update_shopify_product.apply_async(args=[store.id, shopify_product['id']], countdown=5)

                return JsonResponse({'status': 'ok'})

            elif topic == 'products/delete':
                product.monitor_id = 0  # TODO: Remove from Price Monitor Service
                product.shopify_id = 0

                try:
                    images = json.load(product.get_original_data()).get('images')
                    if images:
                        product.update_data({'images': images})
                except:
                    pass

                product.save()

                ProductChange.objects.filter(shopify_product=product).delete()

                ShopifyProductImage.objects.filter(store=store, product=shopify_product['id']).delete()

                return JsonResponse({'status': 'ok'})

            elif topic == 'orders/create' or topic == 'orders/updated':
                new_order = topic == 'orders/create'
                queue = 'priority_high' if new_order else 'celery'
                countdown = 1 if new_order else random.randint(2, 9)

                cache.set('webhook_order_{}_{}'.format(store.id, shopify_order['id']), shopify_order, timeout=600)
                countdown_key = 'eta_order__{}_{}_{}'.format(store.id, shopify_order['id'], topic.split('/').pop())
                countdown_saved = cache.get(countdown_key)
                if countdown_saved is None:
                    cache.set(countdown_key, countdown, timeout=countdown * 2)
                else:
                    countdown = countdown_saved + random.randint(2, 5)
                    cache.set(countdown_key, countdown, timeout=countdown * 2)

                tasks.update_shopify_order.apply_async(
                    args=[store.id, shopify_order['id']],
                    queue=queue,
                    countdown=countdown)

                # if store.user.can('fulfillbox.use'):
                #     from shopify_orders.tasks import fulfill_shopify_order_line
                #     _order, customer_address = utils.shopify_customer_address(shopify_order)
                #     if topic == 'orders/create' and shopify_order['financial_status'] == 'paid':
                #         fulfill_shopify_order_line.delay(store.id, shopify_order, customer_address)

                cache.delete(make_template_fragment_key('orders_status', [store.id]))

                return JsonResponse({'status': 'ok'})

            elif topic == 'orders/delete':
                shopify_orders_utils.delete_shopify_order(store, shopify_order)
                return JsonResponse({'status': 'ok'})

            elif topic == 'shop/update':
                if shop_data.get('name'):
                    store.title = shop_data.get('name')
                    store.currency_format = shop_data.get('money_in_emails_format')
                    store.refresh_info(info=shop_data, commit=False)
                    store.save()

                    if store.user.profile.from_shopify_app_store() and shop_data.get('email'):
                        store.user.email = shop_data.get('email')
                        store.user.save()

                    return JsonResponse({'status': 'ok'})

            elif topic == 'app/uninstalled':
                from product_alerts.utils import unmonitor_store

                store.is_active = False
                store.uninstalled_at = timezone.now()
                store.save()

                utils.detach_webhooks(store, delete_too=True)

                unmonitor_store(store)

                if store.user.profile.from_shopify_app_store():
                    # Switch to free plan and disable trial
                    store.user.profile.change_plan(GroupPlan.objects.get(
                        payment_gateway='shopify',
                        slug='shopify-free-plan'))

                return JsonResponse({'status': 'ok'})
            else:
                raise Exception('WEBHOOK: options not found: {}'.format(topic))
        except:
            raven_client.captureException()

            return JsonResponse({'status': 'ok', 'warning': 'Processing exception'})

    elif provider == 'gdpr-shopify' and request.method == 'POST':
        try:
            data = json.loads(request.body)
            for store in ShopifyStore.objects.filter(shop=data.get('shop_domain'), is_active=False):
                try:
                    utils.verify_shopify_webhook(store, request)
                except:
                    raven_client.captureException(level='warning')
                    continue

                topic = option.replace('-', '/')

                if topic == 'delete/customer':
                    # Erase from elasticsearch
                    es = shopify_orders_utils.get_elastic()
                    es_search_enabled = es and shopify_orders_utils.is_store_indexed(store=store)

                    if es_search_enabled:
                        es.delete_by_query(
                            index='shopify-order',
                            doc_type='order',
                            body={
                                'query': {
                                    'terms': {
                                        '_id': data.get('orders_to_redact')
                                    }
                                }
                            }
                        )

                    # Erase from database
                    ShopifyOrder.objects.filter(
                        store=store,
                        order_id__in=data.get('orders_to_redact'),
                    ).delete()

                elif topic == 'delete/store':
                    if not store.is_active:
                        store.delete_request_at = timezone.now()
                        store.save()

                else:
                    raven_client.captureMessage('Shopify GDPR Topic', level='warning', extra={'topic': topic})

            return HttpResponse('ok')
        except:
            raven_client.captureException()

            return JsonResponse({'status': 'ok', 'warning': 'Processing exception'}, status=500)

    elif provider == 'stripe' and request.method == 'POST':
        assert option == 'subs'

        event = json.loads(request.body)

        try:
            return process_webhook_event(request, event['id'], raven_client)
        except:
            if settings.DEBUG:
                traceback.print_exc()

            raven_client.captureException()
            return HttpResponse('Server Error', status=500)

    elif provider in ['instapage', 'instantpage'] and option == 'register':
        try:
            email = request.POST['Email']
            fullname = request.POST['Name']

            intercom_attrs = {
                "register_source": request.GET.get('register_source', 'instapage'),
                "register_medium": request.GET.get('register_medium', 'webhook'),
            }

            user, created = utils.register_new_user(email, fullname, intercom_attributes=intercom_attrs)

            if created:
                raven_client.captureMessage(
                    'InstaPage Registration',
                    level='warning',
                    extra={
                        'name': fullname,
                        'email': email,
                        'exists': User.objects.filter(email__iexact=email).exists()
                    })

                return HttpResponse('ok')
            else:
                raven_client.captureMessage('InstaPage registration email exists', extra={
                    'name': fullname,
                    'email': email,
                    'exists': User.objects.filter(email__iexact=email).exists()
                })

                return HttpResponse('Email is already registed to an other user')

        except:
            raven_client.captureException()

    elif provider == 'clickfunnels' and option == 'register':
        try:
            data = json.loads(request.body)

            email = data['email']
            fullname = data['name']
            funnel_id = str(data['funnel_id'])
            funnel_step_id = str(data['funnel_step_id'])

            if funnel_id != request.GET.get('funnel_id', '4600766') or funnel_step_id != request.GET.get('funnel_step_id', '25561209'):
                return HttpResponse('Ignore Webhook')

            intercom_attrs = {
                "register_source": request.GET.get('register_source', 'clickfunnels'),
                "register_medium": request.GET.get('register_medium', 'webhook'),
            }

            user, created = utils.register_new_user(email, fullname, intercom_attributes=intercom_attrs)

            if created:
                raven_client.captureMessage(
                    'Clickfunnels Registration',
                    level='warning',
                    extra={
                        'name': fullname,
                        'email': email,
                        'exists': User.objects.filter(email__iexact=email).exists()
                    })

                return HttpResponse('ok')
            else:
                raven_client.captureMessage('Clickfunnels registration email exists', extra={
                    'name': fullname,
                    'email': email,
                    'exists': User.objects.filter(email__iexact=email).exists()
                })

                return HttpResponse('Email is already registed to an other user')

        except:
            raven_client.captureException()

    elif provider == 'price-monitor' and request.method == 'POST':
        product_id = request.GET['product']
        dropified_type = request.GET['dropified_type']  # shopify or chq
        if dropified_type == 'shopify':
            try:
                product = ShopifyProduct.objects.get(id=product_id)
            except ShopifyProduct.DoesNotExist:
                return JsonResponse({'error': 'Product Not Found'}, status=404)
        elif dropified_type == 'chq':
            try:
                product = CommerceHQProduct.objects.get(id=product_id)
            except CommerceHQProduct.DoesNotExist:
                return JsonResponse({'error': 'Product Not Found'}, status=404)
        else:
            return JsonResponse({'error': 'Unknown Product Type'}, status=500)

        if product.user.can('price_changes.use') and product.is_connected and product.store.is_active:
            product_change = ProductChange.objects.create(
                store_type=dropified_type,
                shopify_product=product if dropified_type == 'shopify' else None,
                chq_product=product if dropified_type == 'chq' else None,
                user=product.user,
                data=request.body,
            )

            tasks.manage_product_change.apply_async(args=[product_change.pk], countdown=random.randint(1, 120))

        else:
            product.monitor_id = 0
            product.save()
            return JsonResponse({'error': 'User do not have Alerts permission'}, status=404)

        return JsonResponse({'status': 'ok'})

    elif provider == 'slack' and option == 'command':
        request_from = None
        for user in User.objects.filter(is_staff=True):
            if request.POST['user_id'] in user.get_config('_slack_id', ''):
                request_from = user

        if request.POST['command'] == '/store-transfer':
            if not request_from:
                return HttpResponse(':octagonal_sign: _Dropified Support Stuff Only_')

            try:
                text = re.split(' +', request.POST['text'])
                options = {
                    'store': text[0],
                    'from': text[1],
                    'to': text[2],
                    'response_url': request.POST['response_url'],
                }

                print options

            except:
                return HttpResponse(":x: Invalid Command Format")

            try:
                from_user = User.objects.get(id=options['from']) if safeInt(options['from']) else User.objects.get(email__iexact=options['from'])
            except:
                return HttpResponse(":x: {} user not found".format(options['from']))

            try:
                to_user = User.objects.get(id=options['to']) if safeInt(options['to']) else User.objects.get(email__iexact=options['to'])
            except:
                return HttpResponse(":x: {} user not found".format(options['to']))

            shop = re.findall('[^/@\.]+\.myshopify\.com', options['store'])
            if not shop:
                return HttpResponse(':x: Store link is invalid')
            else:
                shop = shop.pop()

            try:
                store = ShopifyStore.objects.get(shop=shop, user=from_user, is_active=True)
                if store.shopifyproduct_set.count() > 10000 or \
                        store.shopifyorder_set.count() > 10000 or \
                        store.shopifyordertrack_set.count() > 10000:
                    return HttpResponse(':x: Store {} have to many Products/Orders, store must be manually transfered'.format(shop))

            except ShopifyStore.DoesNotExist:
                return HttpResponse(':x: Store {} is not found on {} account'.format(shop, from_user.email))

            if not ShopifyStore.objects.filter(shop=shop, user=to_user).count():
                return HttpResponse(':x: Store {} is not install on {} account'.format(shop, to_user.email))

            AdminEvent.objects.create(
                user=request_from,
                target_user=from_user,
                event_type='store_transfer',
                data=json.dumps({'to': to_user.email, 'store': shop}))

            options['store'] = store.id
            options['shop'] = store.shop

            tasks.store_transfer.delay(options)
            return HttpResponse(':hourglass_flowing_sand: Transferring {shop} from {from} to {to} is in progress...'.format(**options))

        elif request.POST['command'] == '/cancel-shopify':
            if not request_from:
                return HttpResponse(':octagonal_sign: _Dropified Support Stuff Only_')

            shop = re.findall('[^/]+.myshopify.com', request.POST['text'])
            if not shop:
                return HttpResponse(':x: Could not find shop in {}'.format(request.POST['text']))

            shop = shop[0]
            found = []

            for store in ShopifyStore.objects.filter(shop=shop, is_active=True):
                for charge in store.shopify.RecurringApplicationCharge.find():
                    if charge.status == 'active':
                        found.append(store.shop)
                        charge.destroy()

            if found:
                return HttpResponse('Charge canceled for *{}*'.format(', '.join(list(set(found)))))
            else:
                return HttpResponse('No Recurring Charges found on *{}*'.format(shop))

        elif request.POST['command'] == '/captcha-credit':
            if not request_from:
                return HttpResponse(':octagonal_sign: _Dropified Support Stuff Only_')

            is_review_bonus = False
            args = request.POST['text'].split(' ')
            if len(args) == 2:
                email = args[0]
                credits = args[1]
                if credits == 'review':
                    credits = 1000
                    is_review_bonus = True
            elif len(args) == 1:
                email = args[0]
                credits = 1000
            else:
                return HttpResponse(':x: Number of arguments is not correct {}'.format(request.POST['text']))

            user = User.objects.get(email=email)

            if is_review_bonus and user.can('unlimited_catpcha.use'):
                user.set_config('_double_orders_limit', arrow.utcnow().timestamp)
                return HttpResponse('{} Double Orders Limit for *{}*'.format(credits, email))

            try:
                captchacredit = CaptchaCredit.objects.get(user=user)
                captchacredit.remaining_credits += credits
                captchacredit.save()

            except CaptchaCredit.DoesNotExist:
                captchacredit.objects.create(
                    user=user,
                    remaining_credits=credits
                )

            return HttpResponse('{} Captcha Credits added to *{}*'.format(credits, email))

        elif request.POST['command'] == '/dash-facebook-reset':
            if not request_from:
                return HttpResponse(':octagonal_sign: _Dropified Support Staff Only_')

            args = request.POST['text'].split(' ')
            access = FacebookAccess.objects

            if len(args) >= 2:
                shop = re.findall('[^/@\.]+\.myshopify\.com', args[1])
                if not shop:
                    return HttpResponse(':x: Store link is invalid')
                else:
                    shop = shop.pop()

            if len(args) == 1:
                access = access.filter(user__email__iexact=args[0])
            elif len(args) == 2:
                access = access.filter(user__email__iexact=args[0], store__shop=shop)
            elif len(args) == 3:
                access = access.filter(user__email__iexact=args[0], store__shop__iexact=shop, facebook_user_id=args[2])
            else:
                return HttpResponse(':x: Number of arguments is not correct: {}'.format(request.POST['text']))

            count, models = access.delete()
            return HttpResponse("Deleted {} Facebook Synced Accounts".format(count))

        elif request.POST['command'] == '/dash-facebook-list':
            if not request_from:
                return HttpResponse(':octagonal_sign: _Dropified Support Staff Only_')

            access_list = FacebookAccess.objects.select_related('store').filter(user__email=request.POST['text'])
            result = []
            for access in access_list:
                accounts = u', '.join([a.account_name for a in access.accounts.all()])
                result.append(u'Store: {} | Facebook: {} | Accounts: {}'.format(
                    access.store.shop,
                    access.facebook_user_id,
                    accounts
                ))

            return HttpResponse('Results:\n{}'.format(u'\n'.join(result if result else ['Not found'])))

        else:
            return HttpResponse(':x: Unknown Command')

    else:
        raven_client.captureMessage('Unknown Webhook Provider')
        return JsonResponse({'status': 'ok', 'warning': 'Unknown provider'}, status=500)


def get_product(request, filter_products, post_per_page=25, sort=None, store=None, board=None, load_boards=False):
    products = []
    paginator = None
    page = request.GET.get('page', 1)
    models_user = request.user.models_user
    user = request.user
    user_stores = request.user.profile.get_shopify_stores(flat=True)
    res = ShopifyProduct.objects.select_related('store') \
                                .defer('variants_map', 'shipping_map', 'notes') \
                                .filter(user=models_user) \
                                .filter(Q(store__in=user_stores) | Q(store=None))
    if store:
        if store == 'c':  # connected
            res = res.exclude(shopify_id=0)
        elif store == 'n':  # non-connected
            res = res.filter(shopify_id=0)

            in_store = utils.safeInt(request.GET.get('in'))
            if in_store:
                in_store = get_object_or_404(ShopifyStore, id=in_store)
                if len(user_stores) == 1:
                    res = res.filter(Q(store=in_store) | Q(store=None))
                else:
                    res = res.filter(store=in_store)

                permissions.user_can_view(user, in_store)
        else:
            store = get_object_or_404(ShopifyStore, id=utils.safeInt(store))
            res = res.filter(shopify_id__gt=0, store=store)

            permissions.user_can_view(user, store)

    if board:
        res = res.filter(shopifyboard=board)
        permissions.user_can_view(user, get_object_or_404(ShopifyBoard, id=board))

    if filter_products:
        res = accept_product(res, request.GET)

    sort = sort if sort else '-date'
    if sort:
        if re.match(r'^-?(title|price|date)$', sort):
            sort_columns = [sort.replace('date', 'created_at')]

            if sort_columns[0].endswith('created_at'):
                sort_columns.append('store_id')

            res = res.order_by(*sort_columns)

    if request.GET.get('product_board') in ['added', 'not_added']:
        board_list = request.user.models_user.shopifyboard_set.all()
        if request.GET.get('product_board') == "added":
            res = res.filter(shopifyboard__in=board_list)
        elif request.GET.get('product_board') == "not_added":
            res = res.exclude(shopifyboard__in=board_list)

    paginator = SimplePaginator(res, post_per_page)

    page = min(max(1, utils.safeInt(page)), paginator.num_pages)
    page = paginator.page(page)
    res = page

    for i in res:
        p = {
            'qelem': i,
            'id': i.id,
            'store': i.store,
            'shopify_url': i.shopify_link(),
            'created_at': i.created_at,
            'updated_at': i.updated_at,
            'product': json.loads(i.data),
        }

        try:
            p['source'] = i.get_original_info(url=p['product']['original_url'])['source']
        except:
            pass

        p['price'] = '%.02f' % utils.safeFloat(p['product'].get('price'))
        p['price'] = money_format(p['price'], i.store)

        price_range = p['product'].get('price_range')
        if price_range and type(price_range) is list and len(price_range) == 2:
            p['price_range'] = '{} - {}'.format(
                money_format('{:.02f}'.format(price_range[0], i.store)),
                money_format('{:.02f}'.format(price_range[1], i.store))
            )

        if 'images' not in p['product'] or not p['product']['images']:
            p['product']['images'] = []

        p['images'] = p['product']['images']

        products.append(p)

    if load_boards and len(products):
        link_product_board(products, request.user.get_boards())

    return products, paginator, page


def link_product_board(products, boards):

    fetch_list = ['p%d-%s' % (i['id'], i['qelem'].updated_at) for i in products]

    for i in boards:
        fetch_list.append('b%d-%s' % (i.id, i.updated_at))

    fetch_key = 'link_product_board_%s' % utils.hash_text(reduce(lambda x, y: '{}.{}'.format(x, y), fetch_list))

    boards = cache.get(fetch_key)
    if boards is None:
        fetched = ShopifyProduct.objects.prefetch_related('shopifyboard_set') \
                                        .only('id') \
                                        .filter(id__in=[i['id'] for i in products])

        boards = {}
        for i in fetched:
            board = i.shopifyboard_set.first()
            boards[i.id] = {'title': board.title} if board else None

        cache.set(fetch_key, boards, timeout=3600)

    for i, v in enumerate(products):
        products[i]['board'] = boards.get(v['id'])

    return products


def accept_product(res, fdata):
    if fdata.get('title'):
        title = decode_params(fdata.get('title'))
        res = res.filter(title=title)

    if fdata.get('price_min') or fdata.get('price_max'):
        min_price = utils.safeFloat(fdata.get('price_min'), -1)
        max_price = utils.safeFloat(fdata.get('price_max'), -1)

        if (min_price > 0 and max_price > 0):
            res = res.filter(price__gte=min_price, price__lte=max_price)

        elif (min_price > 0):
            res = res.filter(price__gte=min_price)

        elif (max_price > 0):
            res = res.filter(price__lte=max_price)

    if fdata.get('type'):
        res = res.filter(product_type__icontains=fdata.get('type'))

    if fdata.get('tag'):
        res = res.filter(tag=fdata.get('tag'))

    if fdata.get('vendor'):
        res = res.filter(default_supplier__supplier_name__icontains=fdata.get('vendor'))

    return res


@login_required
def products_list(request, tpl='grid'):
    store = request.GET.get('store', 'n')

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': settings.ITEMS_PER_PAGE,
        'sort': request.GET.get('sort'),
        'store': store,
        'load_boards': (tpl is None or tpl == 'grid'),
    }

    if args['filter_products'] and not request.user.can('product_filters.use'):
        return render(request, 'upgrade.html')

    products, paginator, page = get_product(**args)

    if not tpl or tpl == 'grid':
        tpl = 'product.html'
    else:
        tpl = 'product_table.html'

    try:
        store = ShopifyStore.objects.get(id=utils.safeInt(store))
    except:
        store = None

    if store:
        try:
            utils.sync_shopify_products(store, products)
        except:
            raven_client.captureException(level='warning')

    breadcrumbs = [{'title': 'Products', 'url': '/product'}]

    if request.GET.get('store', 'n') == 'n':
        breadcrumbs.append({'title': 'Non Connected', 'url': '/product?store=n'})
    elif request.GET.get('store', 'n') == 'c':
        breadcrumbs.append({'title': 'Connected', 'url': '/product?store=c'})

    in_store = utils.safeInt(request.GET.get('in'))
    if in_store:
        in_store = get_object_or_404(request.user.profile.get_shopify_stores(), id=in_store)
    elif store:
        in_store = store

    if in_store:
        breadcrumbs.append({'title': in_store.title, 'url': '/product?store={}'.format(in_store.id)})

    return render(request, tpl, {
        'paginator': paginator,
        'current_page': page,
        'filter_products': args['filter_products'],
        'products': products,
        'store': store,
        'page': 'product',
        'breadcrumbs': breadcrumbs
    })


@login_required
def shopify_migration(request):
    if not request.user.can('product_filters.use'):
        return render(request, 'upgrade.html')

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Migration page.')
        return HttpResponseRedirect('/')

    ppp = min(utils.safeInt(request.GET.get('ppp'), 50), 100)
    page = request.GET.get('page', '1')

    if request.GET.get('reset') == '1':
        request.user.profile.del_config_values('_shopify_products_filter_', True)

    category = utils.get_shopify_products_filter(request, 'category', '')
    status = utils.get_shopify_products_filter(request, 'status', 'any')
    title = utils.get_shopify_products_filter(request, 'title', '')

    if status not in ['connected', 'not_connected', 'any']:
        status = 'any'

    breadcrumbs = [
        {'url': '/product', 'title': 'Products'},
        {'url': '/product?store={}'.format(store.id), 'title': store.title},
    ]

    return render(request, 'shopify_migration.html', {
        'store': store,
        'category': category,
        'status': status,
        'title': title,
        'user_filter': utils.get_shopify_products_filter(request),
        'items_per_page_list': [10, 50, 100],
        'page': 'shopify_migration',
        'breadcrumbs': breadcrumbs,
        'ppp': ppp,
        'current_page': page
    })


@login_required
def product_view(request, pid):
    #  AWS

    aws_available = (settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY and settings.AWS_STORAGE_BUCKET_NAME)

    conditions = [
        ["starts-with", "$utf8", ""],
        # Change this path if you need, but adjust the javascript config
        ["starts-with", "$key", "uploads"],
        ["starts-with", "$name", ""],
        ["starts-with", "$Content-Type", "image/"],
        ["starts-with", "$filename", ""],
        {"bucket": settings.AWS_STORAGE_BUCKET_NAME},
        {"acl": "public-read"}
    ]

    policy = {
        # Valid for 3 hours. Change according to your needs
        "expiration": arrow.now().replace(hours=+3).format("YYYY-MM-DDTHH:mm:ss") + 'Z',
        "conditions": conditions
    }

    policy_str = json.dumps(policy)
    string_to_sign = base64.encodestring(policy_str).replace('\n', '')

    signature = base64.encodestring(
        hmac.new(settings.AWS_SECRET_ACCESS_KEY.encode(), string_to_sign.encode('utf8'), sha1).digest()).strip()

    #  /AWS
    if request.user.is_superuser:
        product = get_object_or_404(ShopifyProduct, id=pid)
        if product.user != request.user:
            messages.warning(request, 'Preview Mode: Other features (like Variant Mapping,'
                                      ' Product info Tab, etc) will not work. '
                                      '<a href="/hijack/{u.id}?next=/product/{p.id}">'
                                      'Login as {u.username}</a>'.format(u=product.user, p=product))
    else:
        product = get_object_or_404(ShopifyProduct, id=pid)
        permissions.user_can_view(request.user, product)

    if not product.store and (not request.user.is_subuser or request.user.models_user.id not in [14970]):  # Intercom 11917013063
        product.store = product.user.profile.get_shopify_stores().first()
        product.save()

    try:
        alert_config = json.loads(product.config)
    except:
        alert_config = {}

    try:
        board = ShopifyBoard.objects.filter(products=product)
    except ShopifyBoard.DoesNotExist:
        board = None

    shopify_product = None
    if product.shopify_id and product.store:
        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)

        if shopify_product:
            shopify_product = utils.link_product_images(shopify_product)

            if arrow.get(shopify_product['updated_at']).datetime > product.updated_at or request.GET.get('sync'):
                tasks.update_shopify_product(
                    product.store.id,
                    product.shopify_id,
                    shopify_product=shopify_product,
                    product_id=product.id)

                product.refresh_from_db()

    p = {
        'qelem': product,
        'id': product.id,
        'store': product.store,
        'user': product.user,
        'created_at': product.created_at,
        'updated_at': product.updated_at,
        'product': json.loads(product.data),
        'notes': product.notes,
        'alert_config': alert_config
    }

    if 'images' not in p['product'] or not p['product']['images']:
        p['product']['images'] = []

    p['price'] = '$%.02f' % utils.safeFloat(p['product'].get('price'))

    p['images'] = p['product']['images']
    p['original_url'] = p['product'].get('original_url')

    if (p['original_url'] and len(p['original_url'])):
        if 'aliexpress' in p['original_url'].lower():
            try:
                p['original_product_id'] = re.findall('([0-9]+).html', p['original_url'])[0]
                p['original_product_source'] = 'ALIEXPRESS'
            except:
                pass

    p['source'] = product.get_original_info()

    original = None
    try:
        original = json.loads(product.get_original_data())
    except:
        pass

    if shopify_product:
        p['shopify_url'] = product.store.get_link('/admin/products/{}'.format(product.shopify_id))
        p['variant_edit'] = '/product/variants/{}/{}'.format(product.store.id, product.shopify_id)

        p['product']['description'] = shopify_product['body_html']
        p['product']['vendor'] = shopify_product['vendor']
        p['product']['published'] = shopify_product['published_at'] is not None

        collections = utils.ProductCollections().get_collections(product.store)
    else:
        collections = None

    breadcrumbs = [{'title': 'Products', 'url': '/product'}]

    if product.store_id:
        breadcrumbs.append({'title': product.store.title, 'url': '/product?store={}'.format(product.store.id)})

    breadcrumbs.append(p['product']['title'])

    return render(request, 'product_view.html', {
        'product': p,
        'board': board,
        'original': original,
        'collections': collections,
        'shopify_product': shopify_product,
        'aws_available': aws_available,
        'aws_policy': string_to_sign,
        'aws_signature': signature,
        'page': 'product',
        'breadcrumbs': breadcrumbs
    })


@login_required
def variants_edit(request, store_id, pid):
    """
    pid: Shopify Product ID
    """

    if not request.user.can('product_variant_setup.use'):
        return render(request, 'upgrade.html')

    store = get_object_or_404(ShopifyStore, id=store_id)
    permissions.user_can_view(request.user, store)

    product = utils.get_shopify_product(store, pid)

    if not product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    return render(request, 'variants_edit.html', {
        'store': store,
        'product_id': pid,
        'product': product,
        'api_url': store.get_link(),
        'page': 'product',
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Edit Variants']
    })


@login_required
def product_mapping(request, product_id):
    product = get_object_or_404(ShopifyProduct, id=product_id)
    permissions.user_can_edit(request.user, product)

    if not product.default_supplier:
        suppliers = product.get_suppliers()
        if len(suppliers):
            product.set_default_supplier(suppliers[0], commit=True)
        else:
            messages.error(request, 'You have to add at least one supplier before using Variants Mapping')
            return HttpResponseRedirect('/product/{}'.format(product.id))

    current_supplier = utils.safeInt(request.GET.get('supplier'))
    if not current_supplier and product.default_supplier:
        current_supplier = product.default_supplier.id

    current_supplier = product.productsupplier_set.get(id=current_supplier)

    shopify_id = product.get_shopify_id()
    if not shopify_id:
        raise Http404("Product doesn't exists on Shopify Store.")

    shopify_product = utils.get_shopify_product(product.store, shopify_id)
    if not shopify_product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    images = {}
    variants_map = product.get_variant_mapping(supplier=current_supplier)
    shopify_variants = {}

    for i in shopify_product['images']:
        for var in i['variant_ids']:
            images[var] = i['src']

    seen_variants = []
    for i, v in enumerate(shopify_product['variants']):
        shopify_product['variants'][i]['image'] = images.get(v['id'])

        mapped = variants_map.get(str(v['id']))
        if mapped:
            options = mapped
        else:
            options = []
            if v.get('option1') and v.get('option1').lower() != 'default title':
                options.append(v.get('option1'))
            if v.get('option2'):
                options.append(v.get('option2'))
            if v.get('option3'):
                options.append(v.get('option3'))

            options = map(lambda a: {'title': a}, options)

        try:
            if type(options) not in [list, dict]:
                options = json.loads(options)

                if type(options) is int:
                    options = str(options)
        except:
            pass

        variants_map[str(v['id'])] = options
        shopify_variants[str(v['id'])] = v
        shopify_product['variants'][i]['default'] = options
        seen_variants.append(str(v['id']))

    for k in variants_map.keys():
        if k not in seen_variants:
            del variants_map[k]

    product_suppliers = {}
    for i in product.get_suppliers():
        product_suppliers[i.id] = {
            'id': i.id,
            'name': i.get_name(),
            'url': i.product_url
        }

    return render(request, 'product_mapping.html', {
        'store': product.store,
        'product_id': product_id,
        'product': product,
        'shopify_product': shopify_product,
        'shopify_variants': shopify_variants,
        'variants_map': variants_map,
        'product_suppliers': product_suppliers,
        'current_supplier': current_supplier,
        'page': 'product',
        'breadcrumbs': [
            {'title': 'Products', 'url': '/product'},
            {'title': product.store.title, 'url': '/product?store={}'.format(product.store.id)},
            {'title': product.title, 'url': '/product/{}'.format(product.id)},
            'Variants Mapping',
        ]
    })


@login_required
def mapping_supplier(request, product_id):
    product = get_object_or_404(ShopifyProduct, id=product_id)
    permissions.user_can_edit(request.user, product)

    shopify_id = product.get_shopify_id()
    if not shopify_id:
        raise Http404("Product doesn't exists on Shopify Store.")

    shopify_product = utils.get_shopify_product(product.store, shopify_id)
    if not shopify_product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    images = {}
    suppliers_map = product.get_suppliers_mapping()

    for i in shopify_product['images']:
        for var in i['variant_ids']:
            images[var] = i['src']

    if not product.default_supplier:
        suppliers = product.get_suppliers()
        if len(suppliers):
            product.set_default_supplier(suppliers[0], commit=True)
        else:
            messages.error(request, 'You have to add at least one supplier before using Variants Mapping')
            return HttpResponseRedirect('/product/{}'.format(product.id))

    default_supplier_id = product.default_supplier.id
    for i, v in enumerate(shopify_product['variants']):
        supplier = suppliers_map.get(str(v['id']), {'supplier': default_supplier_id, 'shipping': {}})
        suppliers_map[str(v['id'])] = supplier

        shopify_product['variants'][i]['image'] = images.get(v['id'])
        shopify_product['variants'][i]['supplier'] = supplier['supplier']
        shopify_product['variants'][i]['shipping'] = supplier['shipping']

    product_suppliers = {}
    for i in product.get_suppliers():
        product_suppliers[i.id] = {
            'id': i.id,
            'name': i.get_name(),
            'url': i.product_url
        }

    shipping_map = product.get_shipping_mapping()
    variants_map = product.get_all_variants_mapping()
    mapping_config = product.get_mapping_config()

    return render(request, 'mapping_supplier.html', {
        'store': product.store,
        'product_id': product_id,
        'product': product,
        'shopify_product': shopify_product,
        'suppliers_map': suppliers_map,
        'shipping_map': shipping_map,
        'variants_map': variants_map,
        'product_suppliers': product_suppliers,
        'mapping_config': mapping_config,
        'countries': get_counrties_list(),
        'page': 'product',
        'breadcrumbs': [
            {'title': 'Products', 'url': '/product'},
            {'title': product.store.title, 'url': '/product/?store={}'.format(product.store.id)},
            {'title': product.title, 'url': '/product/{}'.format(product.id)},
            'Advanced Mapping',
        ]
    })


@login_required
def mapping_bundle(request, product_id):
    product = get_object_or_404(ShopifyProduct, id=product_id)
    permissions.user_can_edit(request.user, product)

    if not product.default_supplier:
        suppliers = product.get_suppliers()
        if len(suppliers):
            product.set_default_supplier(suppliers[0], commit=True)
        else:
            messages.error(request, 'You have to add at least one supplier before using Variants Mapping')
            return HttpResponseRedirect('/product/{}'.format(product.id))

    shopify_id = product.get_shopify_id()
    if not shopify_id:
        raise Http404("Product doesn't exists on Shopify Store.")

    shopify_product = utils.get_shopify_product(product.store, shopify_id)
    if not shopify_product:
        messages.error(request, 'Product not found in Shopify')
        return HttpResponseRedirect('/')

    images = {}

    for i in shopify_product['images']:
        for var in i['variant_ids']:
            images[var] = i['src']

    bundle_mapping = []

    for i, v in enumerate(shopify_product['variants']):
        if images.get(v['id']):
            v['image'] = images.get(v['id'])
        elif shopify_product.get('image') and shopify_product.get('image').get('src'):
            v['image'] = shopify_product['image']['src']

        v['products'] = product.get_bundle_mapping(v['id'], default=[])

        bundle_mapping.append(v)

    return render(request, 'mapping_bundle.html', {
        'store': product.store,
        'product_id': product_id,
        'product': product,
        'shopify_product': shopify_product,
        'bundle_mapping': bundle_mapping,
        'page': 'product',
        'breadcrumbs': [
            {'title': 'Products', 'url': '/product'},
            {'title': product.store.title, 'url': '/product?store={}'.format(product.store.id)},
            {'title': product.title, 'url': '/product/{}'.format(product.id)},
            'Bundle Mapping',
        ]
    })


@login_required
def bulk_edit(request, what):
    if not request.user.can('bulk_editing.use'):
        return render(request, 'upgrade.html')

    if what == 'saved':
        args = {
            'request': request,
            'filter_products': (request.GET.get('f') == '1'),
            'post_per_page': settings.ITEMS_PER_PAGE,
            'sort': request.GET.get('sort'),
            'store': 'n'
        }

        if args['filter_products'] and not request.user.can('product_filters.use'):
            return render(request, 'upgrade.html')

        products, paginator, page = get_product(**args)

        return render(request, 'bulk_edit.html', {
            'products': products,
            'paginator': paginator,
            'current_page': page,
            'filter_products': args['filter_products'],
            'page': 'bulk',
            'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Bulk Edit', 'Saved']
        })

    elif what == 'connected':
        store = get_object_or_404(ShopifyStore, id=request.GET.get('store'))
        permissions.user_can_view(request.user, store)

        product_ids = request.GET.get('products')
        if not product_ids:
            raise Http404

        products = utils.get_shopify_products(
            store=store,
            product_ids=product_ids,
            fields='id,title,product_type,image,variants,vendor,tags')

        return render(request, 'bulk_edit_connected.html', {
            'products': list(products),
            'store': store,
            'page': 'bulk',
            'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Bulk Edit', store.title]
        })

    raise Http404


@login_required
def boards_list(request):
    if not request.user.can('view_product_boards.sub'):
        raise PermissionDenied()

    search_title = request.GET.get('search') or None
    boards_list = request.user.models_user.shopifyboard_set.all()
    if search_title is not None:
        boards_list = boards_list.filter(title__icontains=search_title)
    boards_count = len(boards_list)

    paginator = SimplePaginator(boards_list, 10)
    page = utils.safeInt(request.GET.get('page'), 1)
    page = min(max(1, page), paginator.num_pages)
    current_page = paginator.page(page)

    for board in current_page.object_list:
        board.saved = board.saved_count(request=request)
        board.connected = board.connected_count(request=request)

    return render(request, 'boards_list.html', {
        'current_page': current_page,
        'count': boards_count,
        'paginator': paginator,
        'page': 'boards',
        'breadcrumbs': ['Boards']
    })


@login_required
def boards(request, board_id):
    if not request.user.can('view_product_boards.sub'):
        raise PermissionDenied()

    board = get_object_or_404(ShopifyBoard, id=board_id)
    permissions.user_can_view(request.user, board)

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': settings.ITEMS_PER_PAGE,
        'sort': request.GET.get('sort'),
        'store': request.GET.get('store'),
        'board': board.id
    }

    products, paginator, page = get_product(**args)

    board = {
        'id': board.id,
        'title': board.title,
        'products': products
    }

    return render(request, 'boards.html', {
        'board': board,
        'paginator': paginator,
        'current_page': page,
        'searchable': True,
        'page': 'boards',
        'breadcrumbs': [{'title': 'Boards', 'url': reverse(boards_list)}, board['title']]
    })


def get_shipping_info(request):
    if request.GET.get('chq'):
        from commercehq_core.models import CommerceHQProduct, CommerceHQSupplier
    if request.GET.get('woo'):
        from woocommerce_core.models import WooProduct, WooSupplier
    if request.GET.get('gear'):
        from gearbubble_core.models import GearBubbleProduct, GearBubbleSupplier

    aliexpress_id = request.GET.get('id')
    product = request.GET.get('product')
    supplier = request.GET.get('supplier')

    country = request.GET.get('country', request.user.get_config('_shipping_country', 'US'))
    country_code = aliexpress_country_code_map(country)

    if request.GET.get('selected'):
        request.user.set_config('_shipping_country', country)

    if not aliexpress_id and supplier:
        if request.GET.get('chq'):

            if int(supplier) == 0:
                product = CommerceHQProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = CommerceHQSupplier.objects.get(id=supplier)

        elif request.GET.get('woo'):

            if int(supplier) == 0:
                product = WooProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = WooSupplier.objects.get(id=supplier)

        elif request.GET.get('gear'):

            if int(supplier) == 0:
                product = GearBubbleProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = GearBubbleSupplier.objects.get(id=supplier)

        else:

            if int(supplier) == 0:
                product = ShopifyProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = ProductSupplier.objects.get(id=supplier)

        aliexpress_id = supplier.get_source_id()

    try:
        shippement_data = utils.aliexpress_shipping_info(aliexpress_id, country_code)
    except requests.Timeout:
        raven_client.captureException()

        if request.GET.get('type') == 'json':
            return JsonResponse({'error': 'Aliexpress Server Timeout'}, status=501)
        else:
            return render(request, '500.html', status=500)

    if request.GET.get('type') == 'json':
        return JsonResponse(shippement_data, safe=False)

    if not request.user.is_authenticated:
        return HttpResponseRedirect('%s?%s' % (reverse('login'),
                                               urllib.urlencode({'next': request.get_full_path()})))

    if request.GET.get('chq'):
        product = get_object_or_404(CommerceHQProduct, id=request.GET.get('product'))
    elif request.GET.get('woo'):
        product = get_object_or_404(WooProduct, id=request.GET.get('product'))
    elif request.GET.get('gear'):
        product = get_object_or_404(GearBubbleProduct, id=request.GET.get('product'))
    else:
        product = get_object_or_404(ShopifyProduct, id=request.GET.get('product'))

    permissions.user_can_view(request.user, product)

    product_data = json.loads(product.data)

    if 'store' in product_data:
        store = product_data['store']
    else:
        store = None

    tpl = 'shippement_info.html'
    if request.GET.get('for') == 'order':
        tpl = 'shippement_info_order.html'
    return render(request, tpl, {
        'country_code': country_code,
        'country_name': country_from_code(country),
        'selected_country_code': country,
        'info': shippement_data,
        'store': store
    })


@login_required
def acp_users_list(request):
    if not request.user.is_superuser and not request.user.is_staff:
        raise PermissionDenied()

    random_cache = 0
    q = request.GET.get('q') or request.GET.get('user') or request.GET.get('store')

    if q or cache.get('template.cache.acp_users.invalidate'):
        random_cache = arrow.now().timestamp

    users = User.objects.select_related('profile').defer('profile__config').order_by('-date_joined')

    if request.GET.get('plan', None):
        users = users.filter(profile__plan_id=request.GET.get('plan'))

    registrations_email = None

    if q:
        if request.GET.get('store'):
            users = users.filter(
                Q(shopifystore__id=utils.safeInt(request.GET.get('store'))) |
                Q(shopifystore__shop__iexact=q) |
                Q(commercehqstore__api_url__icontains=q) |
                Q(woostore__api_url__icontains=q) |
                Q(shopifystore__title__icontains=q)
            )
        elif request.GET.get('user') and utils.safeInt(request.GET.get('user')):
            users = users.filter(id=request.GET['user'])
        else:
            if '@' in q:
                users = users.filter(Q(email__icontains=q) | Q(profile__emails__icontains=q))
            elif '.myshopify.com' in q:
                users = users.filter(Q(username__icontains=q) | Q(shopifystore__shop__iexact=q))
            else:
                users = users.filter(
                    Q(username__icontains=q) |
                    Q(email__icontains=q) |
                    Q(profile__emails__icontains=q) |
                    Q(profile__ips__icontains=q) |
                    Q(shopifystore__shop__iexact=q) |
                    Q(commercehqstore__api_url__icontains=q) |
                    Q(woostore__api_url__icontains=q) |
                    Q(shopifystore__title__icontains=q)
                )

        users = users.distinct()

        if not request.user.is_superuser:
            if len(users) > 10:
                limited_users = []

                for i in users:
                    limited_users.append(i)

                    if len(limited_users) > 10:
                        break

                users = limited_users

        profiles = UserProfile.objects.filter(user__in=users)

        if '@' in q:
            registrations_email = q

        AdminEvent.objects.create(
            user=request.user,
            event_type='user_search',
            target_user=users[0] if len(users) == 1 else None,
            data=json.dumps({'query': q}))

    else:
        if not request.user.is_superuser:
            users = User.objects.none()

        profiles = UserProfile.objects.all()

    charges = []
    subscribtions = []
    registrations = []
    user_last_seen = None
    customer_ids = []
    customer_id = request.GET.get('customer_id')
    stripe_customer = None

    if len(users) == 1:
        rep = requests.get('https://dashboard.stripe.com/v1/search', params={
            'count': 20,
            'include[]': 'total_count',
            'query': u'is:customer {}'.format(users[0].email),
            'facets': 'true'
        }, headers={
            'authorization': 'Bearer {}'.format(settings.STRIPE_SECRET_KEY),
            'content-type': 'application/x-www-form-urlencoded',
        })

        rep.raise_for_status()

        if rep.json()['count'] > 0:
            for c in rep.json()['data']:
                customer_ids.append({
                    'id': c['id'],
                    'email': c['email'],
                })

        if customer_id:
            found = False
            for i in customer_ids:
                if customer_id == i['id']:
                    found = True
                    break

            assert found

        if not customer_id:
            if users[0].have_stripe_billing():
                customer_id = users[0].stripe_customer.customer_id
            elif len(customer_ids):
                customer_id = customer_ids[0]['id']

        if customer_id:
            for i in stripe.Charge.list(limit=10, customer=customer_id).data:
                charges.append({
                    'id': i.id,
                    'date': arrow.get(i.created).format('MM/DD/YYYY HH:mm'),
                    'date_str': arrow.get(i.created).humanize(),
                    'status': i.status,
                    'failure_message': i.failure_message,
                    'amount': u'${:0.2f}'.format(i.amount / 100.0),
                    'amount_refunded': u'${:0.2f}'.format(i.amount_refunded / 100.0) if i.amount_refunded else None,
                })

            for i in stripe.Subscription.list(customer=customer_id).data:
                subscribtions.append(i)

            stripe_customer = stripe.Customer.retrieve(customer_id)
            stripe_customer.account_balance = stripe_customer.account_balance / 100.0

        registrations_email = users[0].email

        try:
            from last_seen.models import LastSeen
            user_last_seen = arrow.get(LastSeen.objects.when(users[0], 'website')).humanize()
        except:
            user_last_seen = ''

    if registrations_email:
        for i in PlanRegistration.objects.filter(email__iexact=registrations_email):
            i.date = arrow.get(i.created_at).format('MM/DD/YYYY HH:mm')
            i.date_str = arrow.get(i.created_at).humanize()

            registrations.append(i)

        if subscribtions and registrations:
            messages.warning(request, 'You have to cancel monthly subscription if the user is on Lifetime plan')

    plans = GroupPlan.objects.all()
    bundles = FeatureBundle.objects.all()

    return render(request, 'acp/users_list.html', {
        'q': q,
        'users': users,
        'plans': plans,
        'bundles': bundles,
        'profiles': profiles,
        'users_count': len(users),
        'customer_id': customer_id,
        'customer_ids': customer_ids,
        'stripe_customer': stripe_customer,
        'last_charges': charges,
        'subscribtions': subscribtions,
        'registrations': registrations,
        'random_cache': random_cache,
        'user_last_seen': user_last_seen,
        'show_products': request.GET.get('products'),
        'page': 'acp_users_list',
        'breadcrumbs': ['ACP', 'Users List']
    })


@login_required
def acp_graph(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    from munch import Munch

    graph_type = request.GET.get('t', 'users')

    days = request.GET.get('days', '30')
    if utils.safeInt(days):
        time_threshold = timezone.now() - timezone.timedelta(days=utils.safeInt(days))
    else:
        time_threshold = None

    data = Munch({
        'graph_type': graph_type,
        'days': days,
        'page': 'acp_graph',
        'breadcrumbs': ['ACP', 'Graph Analytics']
    })

    user = request.GET.get('user')

    if graph_type == 'products':
        data.products = (ShopifyProduct.objects.filter(user=user) if user else ShopifyProduct.objects.all()) \
            .extra({'created': 'date(created_at)'}) \
            .values('created') \
            .annotate(created_count=Count('id')) \
            .order_by('-created')

    if graph_type == 'users':
        data.users = User.objects.all() \
            .extra({'created': 'date(date_joined)'}) \
            .values('created') \
            .annotate(created_count=Count('id')) \
            .order_by('-created')

    if graph_type == 'tracking' and not request.GET.get('aff_only'):
        data.tracking_fulfilled = ShopifyOrderTrack.objects.filter(shopify_status='fulfilled') \
            .extra({'updated': 'date(updated_at)'}) \
            .values('updated') \
            .annotate(updated_count=Count('id')) \
            .order_by('-updated')

        data.tracking_auto = ShopifyOrderTrack.objects.filter(shopify_status='fulfilled', auto_fulfilled=True) \
            .extra({'updated': 'date(updated_at)'}) \
            .values('updated') \
            .annotate(updated_count=Count('id')) \
            .order_by('-updated')

        data.tracking_all = ShopifyOrderTrack.objects.all() \
            .extra({'created': 'date(created_at)'}) \
            .values('created') \
            .annotate(created_count=Count('id')) \
            .order_by('-created')

    if graph_type == 'orders':
        data.shopify_orders = (ShopifyOrder.objects.filter(user=user) if user else ShopifyOrder.objects.all()) \
            .extra({'created': 'date(created_at)'}) \
            .values('created') \
            .annotate(created_count=Count('id')) \
            .order_by('-created')

    if time_threshold:
        for key, val in dict(products='created_at__gt',
                             users='date_joined__gt',
                             tracking_fulfilled='updated_at__gt',
                             tracking_auto='updated_at__gt',
                             tracking_all='created_at__gt',
                             shopify_orders='created_at__gt').iteritems():
            if key in data:
                data[key] = data[key].filter(**{val: time_threshold})

    if not not request.GET.get('aff_only'):
        data.stores_count = ShopifyStore.objects.count()
        data.products_count = (ShopifyProduct.objects.filter(user=user) if user else ShopifyProduct.objects.all()).count()
        data.users_count = User.objects.all().count()

    if graph_type == 'tracking' and not request.GET.get('aff_only'):
        if time_threshold:
            tracking_count = {
                'all': ShopifyOrderTrack.objects.filter(created_at__gt=time_threshold).count(),
                'awaiting': ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='')
                                                     .filter(updated_at__gt=time_threshold).count(),
                'fulfilled': ShopifyOrderTrack.objects.filter(shopify_status='fulfilled')
                                                      .filter(updated_at__gt=time_threshold).count(),
                'auto': ShopifyOrderTrack.objects.filter(shopify_status='fulfilled', auto_fulfilled=True)
                                                 .filter(updated_at__gt=time_threshold).count(),
                'disabled': ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='')
                                                     .filter(updated_at__gt=time_threshold)
                                                     .exclude(Q(store__auto_fulfill='hourly') |
                                                              Q(store__auto_fulfill='daily') |
                                                              Q(store__auto_fulfill='enable')).count()
            }
        else:
            tracking_count = {
                'all': ShopifyOrderTrack.objects.count(),
                'awaiting': ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='').count(),
                'fulfilled': ShopifyOrderTrack.objects.filter(shopify_status='fulfilled').count(),
                'auto': ShopifyOrderTrack.objects.filter(shopify_status='fulfilled', auto_fulfilled=True).count(),
                'disabled': ShopifyOrderTrack.objects.exclude(shopify_status='fulfilled').exclude(source_tracking='')
                                                     .exclude(Q(store__auto_fulfill='hourly') |
                                                              Q(store__auto_fulfill='daily') |
                                                              Q(store__auto_fulfill='enable')).count()

            }

        tracking_count['enabled_awaiting'] = tracking_count['awaiting'] - tracking_count['disabled']
        data.tracking_count = tracking_count

    if request.GET.get('cum'):
        if 'products' in data:
            total_count = data.products_count
            products_cum = []
            for i in data.products:
                total_count -= i['created_count']
                products_cum.append({
                    'created_count': total_count,
                    'created': i['created']
                })
            data.products = products_cum

        if 'users' in data:
            total_count = data.users_count
            users_cum = []
            for i in data.users:
                total_count -= i['created_count']
                users_cum.append({
                    'created_count': total_count,
                    'created': i['created']
                })
            data.users = users_cum

        if 'tracking_fulfilled' in data:
            total_count = tracking_count['fulfilled']
            tracking_fulfilled_cum = []
            for i in data.tracking_fulfilled:
                total_count -= i['updated_count']
                tracking_fulfilled_cum.append({
                    'updated_count': total_count,
                    'updated': i['updated']
                })
            data.tracking_fulfilled = tracking_fulfilled_cum

        if 'tracking_auto' in data:
            total_count = tracking_count['auto']
            tracking_auto_cum = []
            for i in data.tracking_auto:
                total_count -= i['updated_count']
                tracking_auto_cum.append({
                    'updated_count': total_count,
                    'updated': i['updated']
                })
            data.tracking_auto = tracking_auto_cum

        if 'tracking_all' in data:
            total_count = tracking_count['all']
            tracking_all_cum = []
            for i in data.tracking_all:
                total_count -= i['created_count']
                tracking_all_cum.append({
                    'created_count': total_count,
                    'created': i['created']
                })
            data.tracking_all = tracking_all_cum

        if 'shopify_orders' in data:
            total_count = ShopifyOrder.objects.count()
            shopify_orders_cum = []
            for i in data.shopify_orders:
                total_count -= i['created_count']
                shopify_orders_cum.append({
                    'created_count': total_count,
                    'created': i['created']
                })
            data.shopify_orders = shopify_orders_cum

    return render(request, 'acp/graph.html', data.toDict())


@login_required
def acp_groups(request):
    if not request.user.is_superuser and not request.user.has_perm('leadgalaxy.add_planregistration'):
        raise PermissionDenied()

    if request.user.is_superuser:
        if request.method == 'POST':
            if request.POST.get('import'):
                data = json.loads(request.POST.get('import'))
                new_permissions = []
                info = ''
                for i in data:
                    try:
                        AppPermission.objects.get(name=i['name'])
                    except:
                        perm = AppPermission(name=i['name'], description=i['description'])
                        perm.save()

                        new_permissions.append(perm)
                        info = info + '%s: ' % perm.name

                        for p in i['plans']:
                            try:
                                plan = GroupPlan.objects.get(title=p['title'])
                            except:
                                continue
                            plan.permissions.add(perm)

                            info = info + '%s, ' % plan.title

                        info = info + '<br> '

                messages.success(request,
                                 'Permission import success<br> new permissions: %d<br>%s' % (len(new_permissions), info))
            else:
                plan = GroupPlan.objects.get(id=request.POST['default-plan'])
                GroupPlan.objects.all().update(default_plan=0)
                plan.default_plan = 1
                plan.save()

        elif request.GET.get('perm-name'):
            name = request.GET.get('perm-name').strip()
            description = request.GET.get('perm-description').strip()
            perms = []

            if request.GET.get('perm-view'):
                perm = AppPermission(name='%s.view' % name, description='%s | View' % description)
                perm.save()

                perms.append(perm)

            if request.GET.get('perm-use'):
                perm = AppPermission(name='%s.use' % name, description='%s | Use' % description)
                perm.save()

                perms.append(perm)

            for i in request.GET.getlist('perm-grant-to'):
                plan = GroupPlan.objects.get(id=i)
                for p in perms:
                    plan.permissions.add(p)

            messages.success(request, 'New permission added.')
            return HttpResponseRedirect('/acp/groups?add=1')

        elif request.GET.get('export'):
            data = []
            for i in AppPermission.objects.all():
                perm = {
                    'name': i.name,
                    'description': i.description,
                    'plans': []
                }

                for p in i.groupplan_set.all():
                    perm['plans'].append({
                        'id': p.id,
                        'title': p.title
                    })

                data.append(perm)

            return JsonResponse(data, safe=False)

    if request.user.is_superuser:
        plans = GroupPlan.objects.all().order_by('-payment_gateway', 'id')
        tpl = 'acp/groups.html'
    else:
        plans = GroupPlan.objects.filter(id=8)
        tpl = 'acp/groups_limited.html'

    return render(request, tpl, {
        'plans': plans,
        'page': 'acp_groups',
        'breadcrumbs': ['ACP', 'Plans &amp; Groups']
    })


@login_required
def acp_groups_install(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    plan = GroupPlan.objects.get(id=request.GET.get('default'))
    vip_plan = GroupPlan.objects.get(id=request.GET.get('vip'))
    users = User.objects.filter(profile__plan=None)

    if (request.GET.get('confirm', 'no') != 'yes'):
        default_count = 0
        vip_count = 0
        for user in users:
            if 'VIP Members' in user.groups.all().values_list('name', flat=True):
                vip_count += 1
            else:
                default_count += 1

        return HttpResponse('Total: %d - Default: %d - VIP: %d' % (default_count + vip_count, default_count, vip_count))

    count = 0
    with transaction.atomic():
        for user in users:
            if 'VIP Members' in user.groups.all().values_list('name', flat=True):
                profile = UserProfile(user=user, plan=vip_plan)
            else:
                profile = UserProfile(user=user, plan=plan)

            profile.save()

            count += 1

    return HttpResponse('Done, changed: %d' % count)


@login_required
def acp_users_emails(request):
    if not request.user.is_superuser:
        return HttpResponseRedirect('/')

    res = ShopifyProduct.objects.exclude(shopify_id=0)
    users = []
    filtred = []
    for row in res:
        if row.user not in users and row.user not in filtred and 'VIP' not in row.user.profile.plan.title:
            users.append(row.user)
        else:
            filtred.append(row.user)

    o = ''
    for i in users:
        o = '{}{}<br>\n'.format(o, i.email)

    return HttpResponse(o)


def autocomplete(request, target):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User login required'})

    q = request.GET.get('query', '').strip()
    if not q:
        q = request.GET.get('term', '').strip()

    if not q:
        return JsonResponse({'query': q, 'suggestions': []}, safe=False)

    if target == 'types':
        types = []
        for product in request.user.models_user.shopifyproduct_set.only('product_type').filter(product_type__icontains=q)[:10]:
            if product.product_type not in types:
                types.append(product.product_type)

        return JsonResponse({'query': q, 'suggestions': [{'value': i, 'data': i} for i in types]}, safe=False)

    if target == 'vendor':
        suppliers = []
        for supplier in ProductSupplier.objects.filter(store__in=request.user.profile.get_shopify_stores(), supplier_name__icontains=q)[:10]:
            if supplier.supplier_name and supplier.supplier_name not in suppliers:
                suppliers.append(supplier.supplier_name)

        return JsonResponse({'query': q, 'suggestions': [{'value': i, 'data': i} for i in suppliers]}, safe=False)

    elif target == 'tags':
        tags = []
        for product in request.user.models_user.shopifyproduct_set.only('tag').filter(tag__icontains=q)[:10]:
            for i in product.tag.split(','):
                i = i.strip()
                if i and i not in tags:
                    if q.lower() in i.lower():
                        tags.append(i)

        if 'term' in request.GET:
            return JsonResponse(tags, safe=False)
        else:
            return JsonResponse({'query': q, 'suggestions': [{'value': j, 'data': j} for j in tags]}, safe=False)

    elif target == 'title':
        results = []
        products = request.user.models_user.shopifyproduct_set.only('id', 'title', 'data').filter(title=q, shopify_id__gt=0)
        store = request.GET.get('store')
        if store:
            products = products.filter(store=store)

        for product in products[:10]:
            results.append({
                'value': (truncatewords(product.title, 10) if request.GET.get('trunc') else product.title),
                'data': product.id,
                'image': product.get_image()
            })

        return JsonResponse({'query': q, 'suggestions': results}, safe=False)

    elif target == 'supplier-name':
        try:
            store = ShopifyStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except PermissionDenied:
            raven_client.captureException()
            return JsonResponse({'error': 'Permission Denied'}, status=403)

        suppliers = ProductSupplier.objects.only('supplier_name') \
                                           .distinct('supplier_name') \
                                           .filter(store=store) \
                                           .filter(supplier_name__icontains=q)

        results = []
        for supplier in suppliers[:10]:
            results.append({'value': supplier.supplier_name})

        return JsonResponse({'query': q, 'suggestions': results}, safe=False)
    elif target == 'collections':
        results = []
        store = ShopifyStore.objects.get(pk=request.GET.get('store', 0))
        collections = utils.ProductCollections().get_collections(store, q)

        for collection in collections:
            data = {'text': collection.get('title'), 'id': collection.get('id')}
            if data and data not in results:
                if q:
                    if q.lower() in data.get('text').lower():
                        results.append(data)
                else:
                    results.append(data)

        return JsonResponse({'query': q, 'suggestions': results}, safe=False)
    elif target == 'shipping-method-name':
        try:
            store = ShopifyStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except PermissionDenied:
            raven_client.captureException()
            return JsonResponse({'error': 'Permission Denied'}, status=403)

        shipping_methods = ShopifyOrderShippingLine.objects.only('title') \
                                                           .distinct('title') \
                                                           .filter(title=q) \
                                                           .filter(store=store)

        results = []
        for shipping_method in shipping_methods:
            results.append({'value': shipping_method.title})

        return JsonResponse({'query': q, 'suggestions': results}, safe=False)

    elif target == 'variants':
        try:
            store = ShopifyStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

            product = ShopifyProduct.objects.get(id=request.GET.get('product'))
            permissions.user_can_edit(request.user, product)

            shopify_product = utils.get_shopify_product(store, product.shopify_id, raise_for_status=True)

            images = {}
            for i in shopify_product['images']:
                for var in i['variant_ids']:
                    images[var] = i['src']

            for i, v in enumerate(shopify_product['variants']):
                if images.get(v['id']):
                    shopify_product['variants'][i]['image'] = images.get(v['id'])
                elif shopify_product.get('image') and shopify_product.get('image').get('src'):
                    shopify_product['variants'][i]['image'] = shopify_product['image']['src']

            results = []
            for v in shopify_product['variants']:
                results.append({
                    'value': v['title'],
                    'data': v['id'],
                    'image': v.get('image')
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

        except ShopifyProduct.DoesNotExist:
            return JsonResponse({'error': 'Product not found'}, status=404)

    elif target == 'shopify-customer':
        try:
            store = ShopifyStore.objects.get(id=request.GET.get('store'))
            permissions.user_can_view(request.user, store)

            rep = requests.get(url=store.get_link('/admin/customers/search.json', api=True), params={'query': q})
            rep.raise_for_status()

            results = []
            for v in rep.json()['customers']:
                results.append({
                    'value': u'{} {} ({})'.format(v['first_name'] or '', v['last_name'] or '', v['email']).strip(),
                    'data': v['id'],
                })

            return JsonResponse({'query': q, 'suggestions': results}, safe=False)

        except ShopifyStore.DoesNotExist:
            return JsonResponse({'error': 'Store not found'}, status=404)

    else:
        return JsonResponse({'error': 'Unknown target'})


@login_required
def upload_file_sign(request):
    if not request.user.can('image_uploader.use'):
        return JsonResponse({'error': 'You don\'t have access to this feature.'})

    object_name = urllib.quote_plus(request.GET.get('file_name'))
    mime_type = request.GET.get('file_type')

    if 'image' not in mime_type.lower():
        return JsonResponse({'error': 'None allowed file type'})

    expires = int(time.time() + 60 * 60 * 24)
    amz_headers = "x-amz-acl:public-read"

    string_to_sign = "PUT\n\n%s\n%d\n%s\n/%s/%s" % (mime_type, expires, amz_headers, settings.AWS_STORAGE_BUCKET_NAME, object_name)

    signature = base64.encodestring(hmac.new(settings.AWS_SECRET_ACCESS_KEY.encode(), string_to_sign.encode('utf8'), sha1).digest())
    signature = urllib.quote_plus(signature.strip())

    url = 'https://%s.s3.amazonaws.com/%s' % (settings.AWS_STORAGE_BUCKET_NAME, object_name)

    content = {
        'signed_request': '%s?AWSAccessKeyId=%s&Expires=%s&Signature=%s' % (url, settings.AWS_ACCESS_KEY_ID, expires, signature),
        'url': url,
    }

    return JsonResponse(content, safe=False)


@login_required
@ensure_csrf_cookie
def user_profile(request):
    profile = request.user.profile
    bundles = profile.bundles.all().values_list('register_hash', flat=True)
    extra_bundles = []

    if profile.plan.register_hash == '5427f85640fb78728ec7fd863db20e4c':  # JVZoo Pro Plan
        if 'b961a2a0f7101efa5c79b8ac80b75c47' not in bundles:  # JVZoo Elite Bundle
            extra_bundles.append({
                'title': 'Add Elite Bundle',
                'url': 'http://www.dropified.com/elite',
            })

        if '2fba7df0791f67b61581cfe37e0d7b7d' not in bundles:  # JVZoo Unlimited
            extra_bundles.append({
                'title': 'Add Unlimited Bundle',
                'url': 'http://www.dropified.com/unlimited',
            })

    bundles = profile.bundles.filter(hidden_from_user=False)
    stripe_plans = GroupPlan.objects.exclude(Q(stripe_plan=None) | Q(hidden=True)) \
                                    .exclude(payment_interval='yearly') \
                                    .annotate(num_permissions=Count('permissions')) \
                                    .order_by('num_permissions')

    stripe_plans_yearly = GroupPlan.objects.exclude(Q(stripe_plan=None) | Q(hidden=True)) \
                                   .filter(payment_interval='yearly') \
                                   .annotate(num_permissions=Count('permissions')) \
                                   .order_by('num_permissions')

    shopify_plans = GroupPlan.objects.filter(payment_gateway='shopify', hidden=False) \
                                     .exclude(payment_interval='yearly') \
                                     .annotate(num_permissions=Count('permissions')) \
                                     .order_by('num_permissions')

    shopify_plans_yearly = GroupPlan.objects.filter(payment_gateway='shopify', hidden=False) \
                                            .filter(payment_interval='yearly') \
                                            .annotate(num_permissions=Count('permissions')) \
                                            .order_by('num_permissions')

    clippingmagic_plans = ClippingMagicPlan.objects.all()
    clippingmagic = None
    if not request.user.profile.plan.is_free:
        try:
            clippingmagic = ClippingMagic.objects.get(user=request.user)

        except ClippingMagic.DoesNotExist:
            clippingmagic = ClippingMagic.objects.create(user=request.user, remaining_credits=5)

    captchacredit_plans = CaptchaCreditPlan.objects.all()
    captchacredit = None
    if not request.user.profile.plan.is_free:
        try:
            captchacredit = CaptchaCredit.objects.get(user=request.user)

        except CaptchaCredit.DoesNotExist:
            captchacredit = CaptchaCredit.objects.create(user=request.user, remaining_credits=0)

    stripe_customer = request.user.profile.plan.is_stripe() or request.user.profile.plan.is_free
    shopify_apps_customer = request.user.profile.from_shopify_app_store()

    if not request.user.is_subuser and stripe_customer:
        sync_subscription(request.user)

    try:
        affiliate = request.user.lead_dyno_affiliation
    except:
        affiliate = None

    return render(request, 'user/profile.html', {
        'countries': get_counrties_list(),
        'now': timezone.now(),
        'extra_bundles': extra_bundles,
        'bundles': bundles,
        'stripe_plans': stripe_plans,
        'stripe_plans_yearly': stripe_plans_yearly,
        'shopify_plans': shopify_plans,
        'shopify_plans_yearly': shopify_plans_yearly,
        'stripe_customer': stripe_customer,
        'shopify_apps_customer': shopify_apps_customer,
        'clippingmagic_plans': clippingmagic_plans,
        'clippingmagic': clippingmagic,
        'captchacredit_plans': captchacredit_plans,
        'captchacredit': captchacredit,
        'affiliate': affiliate,
        'example_dates': [arrow.utcnow().replace(days=-2).format('MM/DD/YYYY'), arrow.utcnow().replace(days=-2).humanize()],
        'page': 'user_profile',
        'breadcrumbs': ['Profile']
    })


def user_unlock(request, token):
    data = cache.get('unlock_account_{}'.format(token))
    if data:
        username_hash = utils.hash_text(data['username'].lower())

        cache.delete('login_attempts_{}'.format(username_hash))
        cache.delete('unlock_email_{}'.format(username_hash))
        cache.delete('unlock_account_{}'.format(token))

    messages.success(request, 'Your account has been unlocked')

    return HttpResponseRedirect('/')


@login_required
def upgrade_required(request):
    return render(request, 'upgrade.html')


@login_required
def pixlr_close(request):
    return render(request, 'partial/pixlr_close.html')


@login_required
def pixlr_serve_image(request):
    if not request.user.can('pixlr_photo_editor.use'):
        raise PermissionDenied()

    img_url = request.GET.get('image')
    if not img_url:
        raise Http404

    return HttpResponseRedirect(app_link('api/ali/get-image', url=img_url))


@login_required
def save_image_s3(request):
    """Saves the image in img_url into S3 with the name img_name"""

    if 'advanced' in request.GET:
        # Pixlr
        if not request.user.can('pixlr_photo_editor.use'):
            return render(request, 'upgrade.html')

        # TODO: File size limit
        image = request.FILES.get('image')
        product_id = request.GET.get('product')
        img_url = image.name
        old_url = request.GET.get('old_url')

        fp = image

    elif 'clippingmagic' in request.POST:
        if not request.user.can('clippingmagic.use'):
            return render(request, 'upgrade.html')

        product_id = request.POST.get('product')
        img_url = request.POST.get('url')
        old_url = request.POST.get('old_url')
        fp = StringIO.StringIO(requests.get(img_url).content)
        img_url = '%s.png' % img_url

    else:
        # Aviary
        if not request.user.can('aviary_photo_editor.use'):
            return render(request, 'upgrade.html')

        product_id = request.POST.get('product')
        img_url = request.POST.get('url')
        old_url = request.POST.get('old_url')

        if not utils.upload_from_url(img_url, request.user.profile.import_stores()):
            raven_client.captureMessage('Upload from URL', level='warning', extra={'url': img_url})

        fp = StringIO.StringIO(requests.get(img_url).content)

    # Randomize filename in order to not overwrite an existing file
    img_name = utils.random_filename(img_url.split('/')[-1])
    img_name = 'uploads/u%d/%s' % (request.user.id, img_name)
    mimetype = mimetypes.guess_type(img_url)[0]

    upload_url = utils.aws_s3_upload(
        filename=img_name,
        fp=fp,
        mimetype=mimetype,
        bucket_name=settings.S3_UPLOADS_BUCKET
    )

    if request.GET.get('chq') or request.POST.get('chq'):
        from commercehq_core.models import CommerceHQProduct, CommerceHQUserUpload

        product = CommerceHQProduct.objects.get(id=product_id)
        permissions.user_can_edit(request.user, product)
        CommerceHQUserUpload.objects.create(user=request.user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            update_product_data_images(product, old_url, upload_url)

    elif request.GET.get('woo') or request.POST.get('woo'):
        from woocommerce_core.models import WooProduct, WooUserUpload

        product = WooProduct.objects.get(id=product_id)
        permissions.user_can_edit(request.user, product)

        WooUserUpload.objects.create(user=request.user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            update_product_data_images(product, old_url, upload_url)

    elif request.GET.get('gear') or request.POST.get('gear'):
        from gearbubble_core.models import GearBubbleProduct, GearUserUpload

        product = GearBubbleProduct.objects.get(id=product_id)
        permissions.user_can_edit(request.user, product)
        GearUserUpload.objects.create(user=request.user.models_user, product=product, url=upload_url[:510])

        if old_url and not old_url == upload_url:
            update_product_data_images(product, old_url, upload_url)

    else:
        product = ShopifyProduct.objects.get(id=product_id)
        permissions.user_can_edit(request.user, product)
        UserUpload.objects.create(user=request.user.models_user, product=product, url=upload_url[:510])

    # For Pixlr upload, trigger the close of the editor
    if 'advanced' in request.GET:
        product.store.pusher_trigger('pixlr-editor', {
            'success': True,
            'product': product_id,
            'url': upload_url,
            'image_id': request.GET.get('image_id'),
        })

    return JsonResponse({
        'status': 'ok',
        'url': upload_url
    })


def orders_view(request):
    try:
        if not request.user.is_authenticated:
            mixing = ApiResponseMixin()
            user = mixing.get_user(request)
            if user:
                user.backend = settings.AUTHENTICATION_BACKENDS[0]
                login(request, user)
                request.user = user

    except ApiLoginException:
        return redirect('%s?next=%s%%3F%s' % (settings.LOGIN_URL, request.path, urllib.quote_plus(request.GET.urlencode())))

    except:
        raven_client.captureException()

    if not request.user.can('orders.use'):
        return render(request, 'upgrade.html')

    all_orders = []
    store = None
    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Orders page.')
        return HttpResponseRedirect('/')

    if not request.user.can('place_orders.sub', store):
        messages.warning(request, "You don't have access to this store orders")
        return HttpResponseRedirect('/')

    models_user = request.user.models_user

    if request.GET.get('reset') == '1':
        request.user.profile.del_config_values('_orders_filter_', True)

    breadcrumbs = [
        {'url': '/orders', 'title': 'Orders'},
        {'url': '/orders?store={}'.format(store.id), 'title': store.title},
    ]

    # Check if the extension is up-to-date
    latest_release = cache.get('extension_min_version')
    user_version = request.user.get_config('extension_version')

    # User settings
    order_custom_note = models_user.get_config('order_custom_note')
    epacket_shipping = bool(models_user.get_config('epacket_shipping'))
    auto_ordered_mark = bool(models_user.get_config('auto_ordered_mark', True))
    order_custom_line_attr = bool(models_user.get_config('order_custom_line_attr'))
    use_relative_dates = bool(models_user.get_config('use_relative_dates', True))
    fix_order_variants = models_user.get_config('fix_order_variants')
    fix_aliexpress_address = models_user.get_config('fix_aliexpress_address', False)
    fix_aliexpress_city = models_user.get_config('fix_aliexpress_city', False)
    german_umlauts = models_user.get_config('_use_german_umlauts', False)
    show_actual_supplier = models_user.get_config('_show_actual_supplier', False) or models_user.id in [883, 21064, 24767]
    order_risk_all_getaways = models_user.get_config('_order_risk_all_getaways', False)

    if user_version and latest_release \
            and version_compare(user_version, latest_release) < 0 \
            and cache.get('extension_required', False):
        messages.warning(
            request, 'You are using version <b>{}</b> of the extension, the latest version is <b>{}.</b> '
            '<a href="/pages/13">View Upgrade Instructions</a>'.format(user_version, latest_release))

    # Admitad ID
    admitad_site_id, user_admitad_credentials = utils.get_admitad_credentials(request.user.models_user)

    # Filters
    sort = utils.get_orders_filter(request, 'sort', 'asc')
    status = utils.get_orders_filter(request, 'status', 'open')
    fulfillment = utils.get_orders_filter(request, 'fulfillment', 'unshipped,partial')
    financial = utils.get_orders_filter(request, 'financial', 'paid,partially_refunded')
    sort_field = utils.get_orders_filter(request, 'sort', 'created_at')
    sort_type = utils.get_orders_filter(request, 'desc', checkbox=True)
    connected_only = utils.get_orders_filter(request, 'connected', checkbox=True)
    awaiting_order = utils.get_orders_filter(request, 'awaiting_order', checkbox=True)

    query = decode_params(request.GET.get('query') or request.GET.get('id'))
    query_order = decode_params(request.GET.get('query_order') or request.GET.get('id'))
    query_customer = decode_params(request.GET.get('query_customer'))
    query_customer_id = request.GET.get('query_customer_id')
    query_address = request.GET.getlist('query_address')

    product_filter = request.GET.getlist('product')
    supplier_filter = request.GET.get('supplier_name')
    shipping_method_filter = request.GET.get('shipping_method_name')

    date_now = arrow.get(timezone.now())
    created_at_daterange = request.GET.get('created_at_daterange',
                                           '{}-'.format(date_now.replace(days=-30).format('MM/DD/YYYY')))

    if request.GET.get('shop') or query or query_order or query_customer or query_customer_id:
        status, fulfillment, financial = ['any', 'any', 'any']
        connected_only = False
        awaiting_order = False
        created_at_daterange = None

    if request.GET.get('old') == '1':
        shopify_orders_utils.disable_store_sync(store)
    elif request.GET.get('old') == '0':
        shopify_orders_utils.enable_store_sync(store)

    created_at_start, created_at_end = None, None
    if created_at_daterange:
        try:
            daterange_list = created_at_daterange.split('-')

            tz = timezone.localtime(timezone.now()).strftime(' %z')

            created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime

            if len(daterange_list) > 1 and daterange_list[1]:
                created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                created_at_end = created_at_end.span('day')[1].datetime

        except:
            pass

    store_order_synced = shopify_orders_utils.is_store_synced(store)
    store_sync_enabled = store_order_synced and (shopify_orders_utils.is_store_sync_enabled(store) or request.GET.get('new'))
    support_product_filter = shopify_orders_utils.support_product_filter(store) and models_user.can('exclude_products.use')

    es = shopify_orders_utils.get_elastic()
    es_search_enabled = es and shopify_orders_utils.is_store_indexed(store=store) and not request.GET.get('elastic') == '0'

    if not store_sync_enabled:
        if ',' in fulfillment:
            # Direct API call doesn't support more that one fulfillment status
            fulfillment = 'unshipped'

        if ',' in financial:
            financial = 'paid'

        if created_at_start:
            created_at_start = arrow.get(created_at_start).isoformat()

        if created_at_end:
            created_at_end = arrow.get(created_at_end).isoformat()

        if query:
            order_id = shopify_orders_utils.order_id_from_name(store, query)
        else:
            order_id = None

        open_orders = store.get_orders_count(status, fulfillment, financial,
                                             query=utils.safeInt(order_id, query),
                                             created_range=[created_at_start, created_at_end])
        orders = xrange(0, open_orders)

        paginator = utils.ShopifyOrderPaginator(orders, post_per_page)
        paginator.set_store(store)
        paginator.set_order_limit(post_per_page)
        paginator.set_filter(
            status,
            fulfillment,
            financial,
            created_at_start,
            created_at_end
        )
        paginator.set_reverse_order(sort == 'desc' and sort != 'created_at')
        paginator.set_query(utils.safeInt(order_id, query))

        page = min(max(1, page), paginator.num_pages)
        current_page = paginator.page(page)
        page = current_page

        # Update outdated order data by comparing last update timestamp
        _page = ShopifyOrder.objects.filter(store=store, order_id__in=[i['id'] for i in page])
        _update_page = shopify_orders_utils.sort_orders(page, _page)

        countdown = 1
        for order in _update_page:
            if arrow.get(order['updated_at']).timestamp > order['db_updated_at'] and not settings.DEBUG:
                tasks.update_shopify_order.apply_async(
                    args=[store.id, order['id']],
                    kwarg={'shopify_order': order, 'from_webhook': False},
                    countdown=countdown)

                countdown = countdown + 1

    elif es_search_enabled:
        _must_term = [{'term': {'store': store.id}}]
        _must_not_term = []

        if query_order:
            order_id = shopify_orders_utils.order_id_from_name(store, query_order)

            if order_id:
                _must_term.append({'term': {'order_id': order_id}})
            else:
                source_id = utils.safeInt(query_order.replace('#', '').strip(), 123)
                order_ids = ShopifyOrderTrack.objects.filter(store=store, source_id=source_id) \
                                                     .defer('data') \
                                                     .values_list('order_id', flat=True)
                if len(order_ids):
                    _must_term.append({
                        'bool': {
                            'should': [{'term': {'order_id': i}} for i in order_ids]
                        }
                    })
                else:
                    _must_term.append({'term': {'order_id': utils.safeInt(query_order, 0)}})

        if status == 'open':
            _must_not_term.append({"exists": {'field': 'closed_at'}})
            _must_not_term.append({"exists": {'field': 'cancelled_at'}})
        elif status == 'closed':
            _must_term.append({"exists": {'field': 'closed_at'}})
        elif status == 'cancelled':
            _must_term.append({"exists": {'field': 'cancelled_at'}})

        if fulfillment == 'unshipped,partial':
            _must_term.append({
                'bool': {
                    'should': [
                        {
                            'bool': {
                                'must_not': [
                                    {"exists": {'field': 'fulfillment_status'}}
                                ]
                            }
                        },
                        {'term': {'fulfillment_status': 'partial'}}
                    ]
                }
            })
        elif fulfillment == 'unshipped':
            _must_not_term.append({"exists": {'field': 'fulfillment_status'}})
        elif fulfillment == 'shipped':
            _must_term.append({'term': {'fulfillment_status': 'fulfilled'}})
        elif fulfillment == 'partial':
            _must_term.append({'term': {'fulfillment_status': 'partial'}})

        if financial == 'paid,partially_refunded':
            _must_term.append({
                'bool': {
                    'should': [
                        {'term': {'financial_status': 'paid'}},
                        {'term': {'financial_status': 'partially_refunded'}}
                    ]
                }
            })
        elif financial != 'any':
            _must_term.append({'term': {'financial_status': financial}})

        if query_customer_id:
            # Search by customer ID first
            _must_term.append({'match': {'customer_id': query_customer_id}})

        elif query_customer:
            # Try to find the customer email in the search query
            customer_email = re.findall(r'[\w\._\+-]+@[\w\.-]+', query_customer)

            if customer_email:
                _must_term.append({'match': {'customer_email': customer_email[0].lower()}})
            else:
                _must_term.append({'match': {'customer_name': query_customer.lower()}})

        if query_address and len(query_address):
            _must_term.append({
                'bool': {
                    'should': [{'term': {'country_code': country_code.lower()}} for country_code in query_address]
                }
            })

        if created_at_start and created_at_end:
            _must_term.append({
                "range": {
                    "created_at": {
                        "gte": created_at_start.isoformat(),
                        "lte": created_at_end.isoformat(),
                    }
                }
            })
        elif created_at_start:
            _must_term.append({
                "range": {
                    "created_at": {
                        "gte": created_at_start.isoformat(),
                    }
                }
            })
        elif created_at_end:
            _must_term.append({
                "range": {
                    "created_at": {
                        "lte": created_at_end.isoformat(),
                    }
                }
            })

        if connected_only == 'true':
            _must_term.append({
                'range': {
                    'connected_items': {
                        'gt': 0
                    }
                }
            })

        if awaiting_order == 'true':
            _must_term.append({
                'range': {
                    'need_fulfillment': {
                        'gt': 0
                    }
                }
            })

        if product_filter:
            should_products = [{'match': {'product_ids': product_id}} for product_id in product_filter]
            _must_term.append({
                'bool': {
                    'should': should_products
                }
            })

        if supplier_filter:
            products = ShopifyProduct.objects.filter(default_supplier__supplier_name=supplier_filter)
            should_products = [{'match': {'product_ids': product.id}} for product in products]
            _must_term.append({
                'bool': {
                    'should': should_products
                }
            })

        if sort_field not in ['created_at', 'updated_at', 'total_price', 'country_code']:
            sort_field = 'created_at'

        body = {
            'query': {
                'bool': {
                    'must': _must_term,
                    'must_not': _must_not_term
                },
            },
            'sort': [{
                sort_field: 'desc' if sort_type == 'true' else 'asc'
            }],
            'size': post_per_page,
            'from': (page - 1) * post_per_page
        }

        matchs = es.search(index='shopify-order', doc_type='order', body=body)
        hits = matchs['hits']['hits']
        orders = ShopifyOrder.objects.filter(id__in=[i['_id'] for i in hits])
        paginator = FakePaginator(xrange(0, matchs['hits']['total']), post_per_page)
        paginator.set_orders(orders)

        page = min(max(1, page), paginator.num_pages)
        current_page = paginator.page(page)
        page = current_page

        open_orders = matchs['hits']['total']

        if open_orders:
            rep = requests.get(
                url=store.get_link('/admin/orders.json', api=True),
                params={
                    'ids': ','.join([str(i['_source']['order_id']) for i in hits]),
                    'status': 'any',
                    'fulfillment_status': 'any',
                    'financial_status': 'any',
                }
            )

            rep.raise_for_status()
            shopify_orders = rep.json()['orders']
            db_orders = ShopifyOrder.objects.filter(id__in=[i['_id'] for i in hits]) \
                                            .only('order_id', 'updated_at', 'closed_at', 'cancelled_at')

            page = shopify_orders_utils.sort_es_orders(shopify_orders, hits, db_orders)

            countdown = 1
            for order in page:
                shopify_update_at = arrow.get(order['updated_at']).timestamp
                if shopify_update_at > order['db_updated_at'] or shopify_update_at > order['es_updated_at']:

                    tasks.update_shopify_order.apply_async(
                        args=[store.id, order['id']],
                        kwarg={'shopify_order': order, 'from_webhook': False},
                        countdown=countdown,
                        expires=1800)

                    countdown = countdown + 1

    else:
        orders = ShopifyOrder.objects.filter(store=store).only('order_id', 'updated_at', 'closed_at', 'cancelled_at')

        if ShopifySyncStatus.objects.get(store=store).sync_status == 6:
            messages.info(request, 'Your Store Orders are being imported')

        if query_order:
            order_id = shopify_orders_utils.order_id_from_name(store, query_order)

            if order_id:
                orders = orders.filter(order_id=order_id)
            else:
                source_id = utils.safeInt(query_order.replace('#', '').strip(), 123)
                order_ids = ShopifyOrderTrack.objects.filter(store=store, source_id=source_id) \
                                                     .defer('data') \
                                                     .values_list('order_id', flat=True)
                if len(order_ids):
                    orders = orders.filter(order_id__in=order_ids)
                else:
                    orders = orders.filter(order_id=utils.safeInt(query_order, 0))

        if created_at_start:
            orders = orders.filter(created_at__gte=created_at_start)

        if created_at_end:
            orders = orders.filter(created_at__lte=created_at_end)

        if utils.safeInt(query_customer_id):
            order_ids = shopify_orders_utils.order_ids_from_customer_id(store, query_customer_id)
            if len(order_ids):
                orders = orders.filter(order_id__in=order_ids)
            else:
                orders = orders.filter(order_id=-1)  # Show Not Found message

        if query_address and len(query_address):
            orders = orders.filter(Q(country_code__in=query_address))

        query = None

        if status == 'open':
            orders = orders.filter(closed_at=None, cancelled_at=None)
        elif status == 'closed':
            orders = orders.exclude(closed_at=None)
        elif status == 'cancelled':
            orders = orders.exclude(cancelled_at=None)

        if fulfillment == 'unshipped,partial':
            orders = orders.filter(Q(fulfillment_status=None) | Q(fulfillment_status='partial'))
        elif fulfillment == 'unshipped':
            orders = orders.filter(fulfillment_status=None)
        elif fulfillment == 'shipped':
            orders = orders.filter(fulfillment_status='fulfilled')
        elif fulfillment == 'partial':
            orders = orders.filter(fulfillment_status='partial')

        if financial == 'paid,partially_refunded':
            orders = orders.filter(Q(financial_status='paid') | Q(financial_status='partially_refunded'))
        elif financial != 'any':
            orders = orders.filter(financial_status=financial)

        if connected_only == 'true':
            if support_product_filter:
                orders = orders.filter(connected_items__gt=0)
            else:
                orders = orders.annotate(connected=Max('shopifyorderline__product_id')).filter(connected__gt=0)

        if awaiting_order == 'true':
            if support_product_filter:
                orders = orders.filter(need_fulfillment__gt=0)
            else:
                orders = orders.annotate(tracked=Count('shopifyorderline__track')).exclude(tracked=F('items_count'))

        if product_filter:
            if request.GET.get('exclude_products'):
                orders = orders.exclude(shopifyorderline__product_id__in=product_filter, items_count__lte=len(product_filter)).distinct()
            else:
                orders = orders.filter(shopifyorderline__product_id__in=product_filter).distinct()

        if supplier_filter:
            orders = orders.filter(shopifyorderline__product__default_supplier__supplier_name=supplier_filter).distinct()

        if shipping_method_filter:
            orders = orders.filter(shipping_lines__title=shipping_method_filter)

        if sort_field in ['created_at', 'updated_at', 'total_price', 'country_code']:
            sort_desc = '-' if sort_type == 'true' else ''

            if sort_field == 'created_at':
                sort_field = 'order_id'

            orders = orders.order_by(sort_desc + sort_field)

        paginator = SimplePaginator(orders, post_per_page)
        page = min(max(1, page), paginator.num_pages)
        current_page = paginator.page(page)
        page = current_page

        open_orders = paginator.count

        if open_orders:
            cache_list = ['{i.order_id}-{i.updated_at}{i.closed_at}{i.cancelled_at}'.format(i=i) for i in page]
            cache_key = 'saved_orders_%s' % utils.hash_list(cache_list)
            shopify_orders = cache.get(cache_key)
            if shopify_orders is None or cache.get('saved_orders_clear_{}'.format(store.id)):
                rep = requests.get(
                    url=store.get_link('/admin/orders.json', api=True),
                    params={
                        'ids': ','.join([str(i.order_id) for i in page]),
                        'status': 'any',
                        'fulfillment_status': 'any',
                        'financial_status': 'any',
                    }
                )

                api_error = None
                try:
                    rep.raise_for_status()
                    shopify_orders = rep.json()['orders']

                except json.JSONDecodeError:
                    api_error = 'Unexpected response content'
                    raven_client.captureException()

                except requests.exceptions.ConnectTimeout:
                    api_error = 'Connection Timeout'
                    raven_client.captureException()

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:
                        api_error = 'API Rate Limit'
                    elif e.response.status_code == 404:
                        api_error = 'Store Not Found'
                    elif e.response.status_code == 402:
                        api_error = 'Your Shopify Store is not on a paid plan'
                    else:
                        api_error = 'Unknown Error {}'.format(e.response.status_code)
                        raven_client.captureException()
                except:
                    api_error = 'Unknown Error'
                    raven_client.captureException()

                if api_error:
                    cache.delete(cache_key)

                    return render(request, 'orders_new.html', {
                        'store': store,
                        'api_error': api_error,
                        'page': 'orders',
                        'breadcrumbs': breadcrumbs
                    })

                cache.set(cache_key, zlib.compress(json.dumps(shopify_orders)), timeout=300)
                cache.delete('saved_orders_clear_{}'.format(store.id))
            else:
                shopify_orders = json.loads(zlib.decompress(shopify_orders))

            page = shopify_orders_utils.sort_orders(shopify_orders, page)

            # Update outdated order data by comparing last update timestamp
            countdown = 1
            for order in page:
                if arrow.get(order['updated_at']).timestamp > order['db_updated_at']:
                    tasks.update_shopify_order.apply_async(
                        args=[store.id, order['id']],
                        kwarg={'shopify_order': order, 'from_webhook': False},
                        countdown=countdown,
                        expires=1800)

                    countdown = countdown + 1
        else:
            page = []

    orders_sync_check_key = 'store_orders_sync_check_{}'.format(store.id)
    if store_sync_enabled and cache.get(orders_sync_check_key) is None:
        tasks.sync_shopify_orders.apply_async(args=[store.id], kwarg={'elastic': es_search_enabled})
        cache.set(orders_sync_check_key, True, timeout=43200)

    products_cache = {}
    auto_orders = models_user.can('auto_order.use')

    orders_cache = {}
    orders_ids = []
    products_ids = []
    for order in page:
        orders_ids.append(order['id'])
        for line in order['line_items']:
            line_id = line.get('product_id')
            products_ids.append(line_id)

    orders_track = {}
    for i in ShopifyOrderTrack.objects.filter(store=store, order_id__in=orders_ids).defer('data'):
        orders_track['{}-{}'.format(i.order_id, i.line_id)] = i

    orders_log = {}
    for i in ShopifyOrderLog.objects.filter(store=store, order_id__in=orders_ids):
        orders_log[i.order_id] = i

    changed_variants = {}
    for i in ShopifyOrderVariant.objects.filter(store=store, order_id__in=orders_ids):
        changed_variants['{}-{}'.format(i.order_id, i.line_id)] = i

    images_list = {}
    res = ShopifyProductImage.objects.filter(store=store, product__in=products_ids)
    for i in res:
        images_list['{}-{}'.format(i.product, i.variant)] = i.image

    products_list = {}
    product_ids = []
    for order in page:
        for line in order['line_items']:
            if line['product_id']:
                product_ids.append(line['product_id'])

    for p in ShopifyProduct.objects.filter(store=store, shopify_id__in=product_ids).select_related('default_supplier'):
        if p.shopify_id not in products_list:
            products_list[p.shopify_id] = p

    product_variants = []
    for index, order in enumerate(page):
        created_at = arrow.get(order['created_at'])
        try:
            created_at = created_at.to(request.session['django_timezone'])
        except:
            pass

        order['date'] = created_at
        order['date_str'] = created_at.format('MM/DD/YYYY')
        order['date_tooltip'] = created_at.format('YYYY/MM/DD HH:mm:ss')
        order['order_url'] = store.get_link('/admin/orders/%d' % order['id'])
        order['order_api_url'] = store.get_link('/admin/orders/%d.json' % order['id'], api=True)
        order['store'] = store
        order['placed_orders'] = 0
        order['connected_lines'] = 0
        order['lines_count'] = len(order['line_items'])
        order['refunded_lines'] = []
        order['order_log'] = orders_log.get(order['id'])
        order['pending_payment'] = (order['financial_status'] == 'pending' and
                                    (order['gateway'] == 'paypal' or 'amazon' in order['gateway'].lower()))

        if type(order['refunds']) is list:
            for refund in order['refunds']:
                for refund_line in refund['refund_line_items']:
                    order['refunded_lines'].append(refund_line['line_item_id'])

        for i, el in enumerate((order['line_items'])):
            if request.GET.get('line_id'):
                if utils.safeInt(request.GET['line_id']) != el['id']:
                    continue

            order['line_items'][i]['refunded'] = el['id'] in order['refunded_lines']

            order['line_items'][i]['image'] = {
                'store': store.id,
                'product': el['product_id'],
                'variant': el['variant_id']
            }

            order['line_items'][i]['image_src'] = images_list.get('{}-{}'.format(el['product_id'], el['variant_id']))

            shopify_order = orders_track.get('{}-{}'.format(order['id'], el['id']))
            changed_variant = changed_variants.get('{}-{}'.format(order['id'], el['id']))

            order['line_items'][i]['shopify_order'] = shopify_order
            order['line_items'][i]['changed_variant'] = changed_variant

            variant_id = changed_variant.variant_id if changed_variant else el['variant_id']
            variant_title = changed_variant.variant_title if changed_variant else el['variant_title']

            order['line_items'][i]['variant_link'] = store.get_link('/admin/products/{}/variants/{}'.format(el['product_id'], variant_id))

            if not el['product_id']:
                if variant_id:
                    product = ShopifyProduct.objects.filter(store=store, title=el['title'], shopify_id__gt=0).first()
                else:
                    product = None
            elif el['product_id'] in products_cache:
                product = products_cache[el['product_id']]
            else:
                product = products_list.get(el['product_id'])

            if shopify_order or el['fulfillment_status'] == 'fulfilled' or (product and product.is_excluded):
                order['placed_orders'] += 1

            country_code = order.get('shipping_address', {}).get('country_code')
            if not country_code:
                country_code = order.get('customer', {}).get('default_address', {}).get('country_code')

            supplier = None
            bundle_data = []
            if product and product.have_supplier():
                if changed_variant:
                    variant_id = changed_variant.variant_id
                    variant_title = changed_variant.variant_title

                    order['line_items'][i]['variant_id'] = variant_id
                    order['line_items'][i]['variant_title'] = variant_title
                else:
                    variant_id = product.get_real_variant_id(variant_id)

                supplier = product.get_suppier_for_variant(variant_id)
                if supplier:
                    shipping_method = product.get_shipping_for_variant(
                        supplier_id=supplier.id,
                        variant_id=variant_id,
                        country_code=country_code)
                else:
                    shipping_method = None

                order['line_items'][i]['product'] = product
                order['line_items'][i]['supplier'] = supplier
                order['line_items'][i]['shipping_method'] = shipping_method

                if fix_order_variants:
                    mapped = product.get_variant_mapping(name=variant_id, for_extension=True, mapping_supplier=True)
                    if not mapped:
                        utils.fix_order_variants(store, order, product)

                bundles = product.get_bundle_mapping(variant_id)
                if bundles:
                    product_bundles = []
                    for idx, b in enumerate(bundles):
                        b_product = ShopifyProduct.objects.filter(id=b['id']).select_related('default_supplier').first()
                        if not b_product:
                            continue

                        b_variant_id = b_product.get_real_variant_id(b['variant_id'])
                        b_supplier = b_product.get_suppier_for_variant(b_variant_id)
                        if b_supplier:
                            b_shipping_method = b_product.get_shipping_for_variant(
                                supplier_id=b_supplier.id,
                                variant_id=b_variant_id,
                                country_code=country_code)
                        else:
                            continue

                        b_variant_mapping = b_product.get_variant_mapping(name=b_variant_id, for_extension=True, mapping_supplier=True)
                        if b_variant_id and b_variant_mapping:
                            b_variants = b_variant_mapping
                        else:
                            b_variants = b['variant_title'].split('/') if b['variant_title'] else ''

                        product_bundles.append({
                            'product': b_product,
                            'supplier': b_supplier,
                            'shipping_method': b_shipping_method,
                            'quantity': b['quantity'] * el['quantity'],
                            'data': b
                        })

                        bundle_data.append({
                            'quantity': b['quantity'] * el['quantity'],
                            'product_id': b_product.id,
                            'source_id': b_supplier.get_source_id(),
                            'order_url': app_link('orders/place', product=b_supplier.get_source_id(), SABundle=True),
                            'variants': b_variants,
                            'shipping_method': b_shipping_method,
                            'country_code': country_code,
                        })

                    order['line_items'][i]['bundles'] = product_bundles
                    order['line_items'][i]['is_bundle'] = len(bundle_data) > 0
                    order['have_bundle'] = True
                else:
                    product_variants.append({'product': product.id, 'variant': variant_id})

                order['connected_lines'] += 1

            products_cache[el['product_id']] = product

            order, customer_address = utils.shopify_customer_address(
                order, aliexpress_fix=fix_aliexpress_address, fix_aliexpress_city=fix_aliexpress_city, german_umlauts=german_umlauts)

            if auto_orders and customer_address and not order['pending_payment']:
                try:
                    order_data = {
                        'id': '{}_{}_{}'.format(store.id, order['id'], el['id']),
                        'quantity': el['quantity'],
                        'shipping_address': customer_address,
                        'order_id': order['id'],
                        'line_id': el['id'],
                        'product_id': product.id if product else None,
                        'source_id': supplier.get_source_id() if supplier else None,
                        'supplier_id': supplier.get_store_id() if supplier else None,
                        'total': utils.safeFloat(el['price'], 0.0),
                        'store': store.id,
                        'order': {
                            'phone': {
                                'number': customer_address.get('phone'),
                                'country': customer_address['country_code']
                            },
                            'note': order_custom_note,
                            'epacket': epacket_shipping,
                            'auto_mark': auto_ordered_mark,  # Auto mark as Ordered
                        },
                        'products': bundle_data,
                        'is_bundle': len(bundle_data) > 0
                    }

                    if order_custom_line_attr and el.get('properties'):
                        item_note = ''

                        for prop in el['properties']:
                            if not prop['name'] or prop['name'].startswith('_'):
                                continue

                            item_note = u'{}{}: {}\n'.format(item_note, prop['name'], prop['value'])

                        if item_note:
                            item_note = u'Here are custom information for the ordered product:\n{}'.format(item_note).strip()

                            order_data['order']['item_note'] = item_note
                            order['line_items'][i]['item_note'] = item_note

                    if product:
                        mapped = product.get_variant_mapping(name=variant_id, for_extension=True, mapping_supplier=True)
                        if variant_id and mapped:
                            order_data['variant'] = mapped
                        else:

                            order_data['variant'] = variant_title.split('/') if variant_title else ''

                    if product and product.have_supplier():
                        orders_cache['order_{}'.format(order_data['id'])] = order_data
                        order['line_items'][i]['order_data_id'] = order_data['id']

                        order['line_items'][i]['order_data'] = order_data
                except:
                    if settings.DEBUG:
                        traceback.print_exc()

                    raven_client.captureException()

        all_orders.append(order)

    bulk_queue = bool(request.GET.get('bulk_queue'))

    active_orders = {}
    for i in orders_ids:
        active_orders['active_order_{}'.format(i)] = True

    caches['orders'].set_many(orders_cache, timeout=86400 if bulk_queue else 21600)
    caches['orders'].set_many(active_orders, timeout=86400 if bulk_queue else 3600)

    if store_order_synced:
        countries = get_counrties_list()
    else:
        countries = []

    if product_filter:
        product_filter = models_user.shopifyproduct_set.filter(id__in=product_filter)

    order_debug = request.session.get('is_hijacked_user') or \
        (request.user.is_superuser and request.GET.get('debug')) or \
        request.user.get_config('_orders_debug') or \
        settings.DEBUG

    if bulk_queue:
        return utils.format_queueable_orders(request, all_orders, current_page)

    return render(request, 'orders_new.html', {
        'orders': all_orders,
        'store': store,
        'paginator': paginator,
        'current_page': current_page,
        'open_orders': open_orders,
        'query_order': query_order,
        'sort': sort_field,
        'sort_type': sort_type,
        'status': status,
        'financial': financial,
        'fulfillment': fulfillment,
        'query': query,
        'connected_only': connected_only,
        'awaiting_order': awaiting_order,
        'product_filter': product_filter,
        'supplier_filter': supplier_filter,
        'shipping_method_filter': shipping_method_filter,
        'shipping_method_filter_enabled': models_user.get_config('shipping_method_filter') and store_order_synced,
        'order_risk_levels_enabled': models_user.get_config('order_risk_levels_enabled'),
        'user_filter': utils.get_orders_filter(request),
        'store_order_synced': store_order_synced,
        'store_sync_enabled': store_sync_enabled,
        'es_search_enabled': es_search_enabled,
        'product_variants': product_variants,
        'countries': countries,
        'created_at_daterange': created_at_daterange,
        'admitad_site_id': admitad_site_id,
        'user_admitad_credentials': user_admitad_credentials,
        'show_actual_supplier': show_actual_supplier,
        'use_relative_dates': use_relative_dates,
        'order_risk_all_getaways': order_risk_all_getaways,
        'order_debug': order_debug,
        'use_fulfillbox': bool(settings.FULFILLBOX_API_URL and models_user.can('fulfillbox.use')),
        'page': 'orders',
        'breadcrumbs': breadcrumbs
    })


@login_required
def orders_track(request):
    if not request.user.can('orders.use'):
        return render(request, 'upgrade.html')

    visited_time = arrow.now().timestamp
    request.user.profile.set_config_value('orders_track_visited_at', visited_time)

    order_map = {
        'order': 'order_id',
        'source': 'source_id',
        'status': 'source_status',
        'tracking': 'source_tracking',
        'add': 'created_at',
        'reason': 'source_status_details',
        'update': 'status_updated_at',
    }

    for k, v in order_map.items():
        order_map['-' + k] = '-' + v

    sorting = request.GET.get('sort', '-update')
    sorting = order_map.get(sorting, 'status_updated_at')

    store = None
    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)
    query = request.GET.get('query')
    tracking_filter = request.GET.get('tracking')
    fulfillment_filter = request.GET.get('fulfillment')
    hidden_filter = request.GET.get('hidden')
    completed = request.GET.get('completed')
    source_reason = request.GET.get('reason')
    days_passed = request.GET.get('days_passed', '')
    date = request.GET.get('date', '{}-'.format(arrow.get(timezone.now()).replace(days=-30).format('MM/DD/YYYY')))

    if query:
        date = None

    created_at_start, created_at_end = None, None
    if date:
        try:
            daterange_list = date.split('-')

            tz = timezone.localtime(timezone.now()).strftime(' %z')

            created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime

            if len(daterange_list) > 1 and daterange_list[1]:
                created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                created_at_end = created_at_end.span('day')[1].datetime

        except:
            pass

    if days_passed == 'expired':
        days_passed = request.user.get_config('sync_delay_notify_days')
        fulfillment_filter = '0'
        tracking_filter = '0'
        hidden_filter = '0'

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Tracking page.')
        return HttpResponseRedirect('/')

    if not request.user.can('place_orders.sub', store):
        messages.warning(request, "You don't have access to this store orders")
        return HttpResponseRedirect('/')

    orders = ShopifyOrderTrack.objects.select_related('store').filter(user=request.user.models_user, store=store).defer('data')

    if query:
        order_id = shopify_orders_utils.order_id_from_name(store, query)

        if order_id:
            orders = orders.filter(order_id=order_id)
        else:
            orders = orders.filter(Q(source_id=utils.clean_query_id(query)) |
                                   Q(source_tracking=query))

    if tracking_filter == '0':
        orders = orders.filter(source_tracking='')
    elif tracking_filter == '1':
        orders = orders.exclude(source_tracking='')

    if fulfillment_filter == '1':
        orders = orders.filter(shopify_status='fulfilled')
    elif fulfillment_filter == '0':
        orders = orders.exclude(shopify_status='fulfilled')

    if hidden_filter == '1':
        orders = orders.filter(hidden=True)
    elif not hidden_filter or hidden_filter == '0':
        orders = orders.exclude(hidden=True)

    if completed == '1':
        orders = orders.exclude(source_status='FINISH')

    if source_reason:
        if source_reason.startswith('_'):
            orders = orders.filter(source_status=source_reason[1:])
        else:
            orders = orders.filter(source_status_details=source_reason)

    errors_list = request.GET.getlist('errors')
    if errors_list:

        if 'none' in errors_list:
            errors_list = ['none']
            orders = orders.filter(errors__lte=0).exclude(errors=None)

        elif 'any' in errors_list:
            errors_list = ['any']
            orders = orders.filter(errors__gt=0)

        elif 'pending' in errors_list:
            errors_list = ['pending']
            orders = orders.filter(errors=None)

        else:
            errors = 0
            for i in errors_list:
                errors |= utils.safeInt(i, 0)

            orders = orders.filter(errors=errors)

    days_passed = utils.safeInt(days_passed)
    if days_passed:
        time_threshold = timezone.now() - timezone.timedelta(days=days_passed)
        orders = orders.filter(created_at__lt=time_threshold)

    if created_at_start:
        orders = orders.filter(created_at__gte=created_at_start)

    if created_at_end:
        orders = orders.filter(created_at__lte=created_at_end)

    sync_delay_notify_days = utils.safeInt(request.user.get_config('sync_delay_notify_days'))
    sync_delay_notify_highlight = request.user.get_config('sync_delay_notify_highlight')
    order_threshold = None
    if sync_delay_notify_days > 0 and sync_delay_notify_highlight:
        order_threshold = timezone.now() - timezone.timedelta(days=sync_delay_notify_days)

    orders = orders.order_by(sorting)

    paginator = SimplePaginator(orders, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    orders = page.object_list

    if len(orders):
        orders = utils.get_tracking_orders(store, orders)

    ShopifyOrderTrack.objects.filter(store=store, id__in=[i.id for i in orders]) \
                             .update(seen=True)

    return render(request, 'orders_track.html', {
        'store': store,
        'orders': orders,
        'date': date,
        'order_threshold': order_threshold,
        'paginator': paginator,
        'current_page': page,
        'errors': errors_list,
        'reason': source_reason,
        'rejected_status': ALIEXPRESS_REJECTED_STATUS,
        'page': 'orders_track',
        'breadcrumbs': [{'title': 'Orders', 'url': '/orders'}, 'Tracking']
    })


def orders_place(request):
    try:
        if not request.user.is_authenticated:
            mixing = ApiResponseMixin()
            user = mixing.get_user(request)
            if user:
                user.backend = settings.AUTHENTICATION_BACKENDS[0]
                login(request, user)
                request.user = user

    except ApiLoginException:
        return redirect('%s?next=%s%%3F%s' % (settings.LOGIN_URL, request.path, urllib.quote_plus(request.GET.urlencode())))

    except:
        raven_client.captureException()

    try:
        assert request.GET['product']

        product = request.GET['product']

        if utils.safeInt(product):
            product = 'https://www.aliexpress.com/item//{}.html'.format(product)

    except:
        raven_client.captureException()
        raise Http404("Product or Order not set")

    ali_api_key, ali_tracking_id, user_ali_credentials = utils.get_aliexpress_credentials(request.user.models_user)
    admitad_site_id, user_admitad_credentials = utils.get_admitad_credentials(request.user.models_user)

    disable_affiliate = request.user.get_config('_disable_affiliate', False)

    redirect_url = False
    if not disable_affiliate:
        if user_admitad_credentials:
            service = 'admitad'
        elif user_ali_credentials:
            service = 'ali'
        else:
            service = 'admitad'

        if service == 'ali' and ali_api_key and ali_tracking_id:
            redirect_url = utils.get_aliexpress_affiliate_url(ali_api_key, ali_tracking_id, product)
            if not redirect_url:
                messages.error(request, "Could not generate Aliexpress Affiliate link using your API Keys")
                return HttpResponseRedirect('/')

        elif service == 'admitad':
            redirect_url = utils.get_admitad_affiliate_url(admitad_site_id, product)

    if not redirect_url:
        redirect_url = product

    for k in request.GET.keys():
        if k.startswith('SA') and k not in redirect_url and request.GET[k]:
            redirect_url = utils.affiliate_link_set_query(redirect_url, k, request.GET[k])

    # Verify if the user didn't pass order limit
    parent_user = request.user.models_user
    plan = parent_user.profile.plan
    if plan.auto_fulfill_limit != -1 and not settings.DEBUG:
        month_start = arrow.utcnow().span('month')[0]

        # This is used for Oberlo migration
        if parent_user.get_config('auto_fulfill_limit_start'):
            auto_start = arrow.get(parent_user.get_config('auto_fulfill_limit_start'))
            if auto_start > month_start:
                month_start = auto_start

        orders_count = parent_user.shopifyordertrack_set.filter(created_at__gte=month_start.datetime)
        orders_count = orders_count.distinct('order_id').order_by('order_id').count()

        auto_fulfill_limit = plan.auto_fulfill_limit
        if parent_user.get_config('_double_orders_limit'):
            auto_fulfill_limit *= 2

        if not auto_fulfill_limit or orders_count + 1 > auto_fulfill_limit:
            messages.error(request, "You have reached your plan auto fulfill limit ({} orders/month)".format(auto_fulfill_limit))
            return HttpResponseRedirect('/')

    # Save Auto fulfill event
    event_data = {}
    order_data = None
    order_key = request.GET.get('SAPlaceOrder')
    if order_key:
        event_key = 'keen_event_{}'.format(request.GET['SAPlaceOrder'])

        if not order_key.startswith('order_'):
            order_key = 'order_{}'.format(order_key)

        order_data = order_data_cache(order_key)
        prefix, store, order, line = order_key.split('_')

    if order_data:
        order_data['url'] = redirect_url
        caches['orders'].set(order_key, order_data, timeout=caches['orders'].ttl(order_key))

    if order_data and settings.KEEN_PROJECT_ID and not cache.get(event_key):
        try:
            store = ShopifyStore.objects.get(id=store)
            permissions.user_can_view(request.user, store)
        except ShopifyStore.DoesNotExist:
            raise Http404('Store not found')

        for k in request.GET.keys():
            if k == 'SAPlaceOrder':
                pass

            elif k == 'product':
                event_data['product'] = request.GET[k]

                if not utils.safeInt(event_data['product']):  # Check if we are using product link or just the ID
                    event_data['product'] = re.findall('[/_]([0-9]+).html', event_data['product'])
                    if event_data['product']:
                        event_data['product'] = event_data['product'][0]

            elif k.startswith('SA'):
                event_data[k[2:].lower()] = request.GET[k]

        affiliate = 'ShopifiedApp'
        if user_admitad_credentials:
            affiliate = 'UserAdmitad'
        elif user_ali_credentials:
            affiliate = 'UserAliexpress'

        event_data.update({
            'user': store.user.username,
            'user_id': store.user_id,
            'store': store.title,
            'store_id': store.id,
            'plan': plan.title,
            'plan_id': plan.id,
            'affiliate': affiliate,
            'sub_user': request.user.is_subuser,
            'total': order_data['total'],
            'quantity': order_data['quantity'],
            'cart': 'SACart' in request.GET
        })

        tasks.keen_add_event.delay("auto_fulfill", event_data)
        cache.set(event_key, True, timeout=3600)

    return HttpResponseRedirect(redirect_url)


@login_required
def locate(request, what):
    from commercehq_core.models import CommerceHQOrderTrack

    if what == 'order':
        aliexpress_id = utils.safeInt(request.GET.get('aliexpress'))

        if aliexpress_id:
            track = ShopifyOrderTrack.objects.filter(user=request.user.models_user, source_id=aliexpress_id).first()
            if track:
                return HttpResponseRedirect(
                    '{}?store={}&query_order={}&new=1&status=any&'
                    'financial=any&fulfillment=any&awaiting_order=false&connected=false'.format(
                        reverse('orders'), track.store.id, aliexpress_id))

            track = CommerceHQOrderTrack.objects.filter(user=request.user.models_user, source_id=aliexpress_id).first()
            if track:
                return HttpResponseRedirect(
                    '{}?store={}&query={}'.format(reverse('chq:orders_list'), track.store.id, aliexpress_id))

    elif what == 'product':
        if request.GET.get('shop') and request.GET.get('id'):
            store = utils.get_store_from_request(request)
            product = store.shopifyproduct_set.filter(shopify_id=request.GET.get('id')).first() if store else None
            if product:
                return HttpResponseRedirect(reverse('product_view', kwargs={'pid': product.id}))

    raise Http404


@login_required
def product_alerts(request):
    if not request.user.can('price_changes.use'):
        return render(request, 'upgrade.html')

    show_hidden = True if request.GET.get('hidden') else False

    product = request.GET.get('product')
    if product:
        product = get_object_or_404(ShopifyProduct, id=product)
        permissions.user_can_view(request.user, product)

    post_per_page = settings.ITEMS_PER_PAGE
    page = utils.safeInt(request.GET.get('page'), 1)

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Alerts page.')
        return HttpResponseRedirect('/')

    ProductChange.objects.filter(user=request.user.models_user,
                                 shopify_product__store=None).delete()

    changes = ProductChange.objects.select_related('shopify_product') \
                                   .select_related('shopify_product__default_supplier') \
                                   .filter(user=request.user.models_user,
                                           shopify_product__store=store)

    if request.user.is_subuser:
        store_ids = request.user.profile.subuser_permissions.filter(
            codename='view_alerts'
        ).values_list(
            'store_id', flat=True
        )
        changes = changes.filter(shopify_product__store_id__in=store_ids)

    if product:
        changes = changes.filter(shopify_product=product)
    else:
        changes = changes.filter(hidden=show_hidden)

    category = request.GET.get('category')
    if category:
        changes = changes.filter(categories__icontains=category)
    product_type = request.GET.get('product_type', '')
    if product_type:
        changes = changes.filter(shopify_product__product_type__icontains=product_type)

    changes = changes.order_by('-updated_at')

    paginator = SimplePaginator(changes, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    changes = page.object_list

    products = []
    product_variants = {}
    for i in changes:
        shopify_id = i.product.get_shopify_id()
        if shopify_id and str(shopify_id) not in products:
            products.append(str(shopify_id))
    try:
        if len(products):
            products = utils.get_shopify_products(store=store, product_ids=products, fields='id,title,variants')
            for p in products:
                product_variants[str(p['id'])] = p['variants']
    except:
        raven_client.captureException()

    inventory_item_ids = []
    for i in changes:
        changes_map = i.get_changes_map(category)
        variants = product_variants.get(str(i.product.get_shopify_id()), None)
        if variants is not None:
            for c in changes_map['variants']['quantity']:
                index = variant_index(i.product, c['sku'], variants, c.get('ships_from_id'), c.get('ships_from_title'))
                if index is not None:
                    inventory_item_id = variants[index]['inventory_item_id']
                    if variants[index]['inventory_management'] == 'shopify' and inventory_item_id not in inventory_item_ids:
                        inventory_item_ids.append(inventory_item_id)

    variant_quantities = {}
    inventories = utils.get_shopify_inventories(store, inventory_item_ids)
    for inventory in inventories:
        variant_quantities[str(inventory['inventory_item_id'])] = inventory['available']

    product_changes = []
    for i in changes:
        change = {'qelem': i}
        change['id'] = i.id
        change['data'] = i.get_data()
        change['changes'] = i.get_changes_map(category)
        change['product'] = i.product
        change['shopify_link'] = i.product.shopify_link()
        change['original_link'] = i.product.get_original_info().get('url')
        variants = product_variants.get(str(i.product.get_shopify_id()), None)
        for c in change['changes']['variants']['quantity']:
            if variants is not None:
                index = variant_index(i.product, c['sku'], variants, c.get('ships_from_id'), c.get('ships_from_title'))
                if index is not None:
                    if variants[index]['inventory_management'] == 'shopify':
                        quantity = variant_quantities.get(str(variants[index]['inventory_item_id']), None)
                        c['shopify_value'] = quantity
                    else:
                        c['shopify_value'] = "Unmanaged"
                else:
                    c['shopify_value'] = "Not Found"
            else:
                c['shopify_value'] = "Not Found"
        for c in change['changes']['variants']['price']:
            if variants is not None:
                index = variant_index(i.product, c['sku'], variants, c.get('ships_from_id'), c.get('ships_from_title'))
                if index is not None:
                    c['shopify_value'] = variants[index]['price']
                else:
                    c['shopify_value'] = "Not Found"
            else:
                c['shopify_value'] = "Not Found"

        product_changes.append(change)

    if not show_hidden:
        ProductChange.objects.filter(user=request.user.models_user) \
                             .filter(id__in=[i['id'] for i in product_changes]) \
                             .update(seen=True)

    # Allow sending notification for new changes
    cache.delete('product_change_%d' % request.user.models_user.id)

    # Delete sidebar alert info cache
    cache.delete(make_template_fragment_key('alert_info', [request.user.id]))

    tpl = 'product_alerts_tab.html' if product else 'product_alerts.html'
    return render(request, tpl, {
        'product_changes': product_changes,
        'show_hidden': show_hidden,
        'product': product,
        'paginator': paginator,
        'current_page': page,
        'page': 'product_alerts',
        'store': store,
        'category': category,
        'product_type': product_type,
        'breadcrumbs': [{'title': 'Products', 'url': '/product'}, 'Alerts']
    })


@login_required
def bundles_bonus(request, bundle_id):
    bundle = get_object_or_404(FeatureBundle, register_hash=bundle_id)
    if request.method == 'POST':
        form = EmailForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            reg = utils.generate_plan_registration(plan=None, bundle=bundle, data={'email': email})

            try:
                user = User.objects.get(email__iexact=email)
                user.profile.bundles.add(bundle)

                reg.expired = True
            except User.DoesNotExist:
                user = None

            reg.save()

            messages.success(request, 'Bundle %s has been added to your account.' % bundle.title)
            return HttpResponseRedirect('/')

    else:
        initial = {}

        if request.user.is_authenticated:
            initial = {'email': request.user.email}

        form = RegisterForm(initial=initial)

    return render(request, "bundles_bonus.html", {
        'form': form,
        'bundle': bundle
    })


@login_required
def products_collections(request, collection):
    post_per_page = settings.ITEMS_PER_PAGE
    page = request.GET.get('page', 1)
    page = max(1, page)

    paginator = utils.ProductsCollectionPaginator([], post_per_page)
    paginator.set_product_per_page(post_per_page)
    paginator.set_current_page(page)
    paginator.set_query(request.GET.get('title'))

    extra_filter = {}
    filter_map = {
        'price_min': 'price_min',
        'price_max': 'price_max',
        'type': 'category',
        'sort': 'order'
    }

    for k, v in filter_map.items():
        if request.GET.get(k):
            extra_filter[v] = request.GET.get(k)

    paginator.set_extra_filter(extra_filter)

    page = paginator.page(page)

    return render(request, 'products_collections.html', {
        'products': page.object_list,
        'paginator': paginator,
        'current_page': page,

        'page': 'products_collections',
        'breadcrumbs': ['Products', 'Collections', 'US']
    })


@login_required
def logout(request):
    user_logout(request)
    return redirect('/')


def register(request, registration=None, subscribe_plan=None):
    if request.user.is_authenticated and not request.user.is_superuser:
        messages.warning(request, 'You are already logged in')
        return HttpResponseRedirect('/')

    funnel_url = 'https://go.dropified.com/choose-your-planxhh5m5e6'
    if request.method == 'GET' and not request.GET and request.path == '/accounts/register':
        return HttpResponseRedirect(funnel_url)

    email = request.GET.get('email', '')
    if email:
        if '@' not in email:
            email = decode_params(email)
        else:
            # Base64 encode the email in url
            params = request.GET.copy()
            params['email'] = encode_params(email)

            return HttpResponseRedirect('{}?{}'.format(request.path, params.urlencode()))

    try_plan = registration and registration.endswith('-try')
    if registration and (registration.endswith('-subscribe') or try_plan):
        slug = registration.replace('-subscribe', '').replace('-try', '')
        subscribe_plan = get_object_or_404(GroupPlan, slug=slug, payment_gateway='stripe')
        if not subscribe_plan.is_stripe():
            raise Http404('Not a Stripe Plan')
        elif subscribe_plan.locked:
            try:
                assert request.GET.get('l') and request.GET.get('l') in subscribe_plan.register_hash
            except:
                raven_client.captureException(level='warning')
                return HttpResponseRedirect(funnel_url)

        registration = None

    if registration:
        # Convert the hash to a PlanRegistration model
        registration = get_object_or_404(PlanRegistration, register_hash=registration)

        if registration.expired:
            if request.user.is_superuser:
                messages.error(request, 'Registration link <i>{}</i> is expired'.format(registration.register_hash))

            return HttpResponseRedirect('/')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        form.set_plan_registration(registration)

        if form.is_valid():
            new_user = form.save()
            new_user.set_config('_tos-accept', True)

            reg_coupon = request.GET.get('cp')
            if reg_coupon:
                new_user.set_config('registration_discount', Signer().unsign(base64.decodestring(reg_coupon)))

            if subscribe_plan:
                try:
                    if try_plan:
                        new_user.set_config('try_plan', True)
                    else:
                        new_user.stripe_customer.can_trial = False
                        new_user.stripe_customer.save()

                except:
                    raven_client.captureException()

            elif registration is None or registration.get_usage_count() is None:
                utils.apply_plan_registrations(form.cleaned_data['email'])
            else:
                utils.apply_shared_registration(new_user, registration)

            new_user = authenticate(username=new_user.username, password=form.cleaned_data['password1'])

            login(request, new_user)

            RegistrationEvent.objects.create(user=request.user)

            utils.wicked_report_add_user(request, new_user)

            if subscribe_plan:
                if not try_plan and not subscribe_plan.is_free:
                    return HttpResponseRedirect("/user/profile?auto={}#billing".format(subscribe_plan.id))
                elif try_plan and not subscribe_plan.is_free:
                    return HttpResponseRedirect("/user/profile?try={}#plan".format(subscribe_plan.id))

            return HttpResponseRedirect("/")

    else:
        try:

            initial = {
                'email': (registration.email if registration else email).strip(),
                'fullname': (request.GET.get('name', '')).strip(),
            }
        except:
            initial = {}

        form = RegisterForm(initial=initial)

    if registration and registration.email:
        form.fields['email'].widget.attrs['readonly'] = True

    reg_coupon = request.GET.get('cp')
    if reg_coupon:
        try:
            reg_coupon = Signer().unsign(base64.decodestring(reg_coupon))
            reg_coupon = stripe.Coupon.retrieve(reg_coupon)
            if reg_coupon.redeem_by <= arrow.utcnow().timestamp:
                reg_coupon = None
            else:
                reg_coupon = reg_coupon.metadata.msg
        except:
            reg_coupon = None
            raven_client.captureException()

        if not reg_coupon:
            raise Http404('Coupon Not Found')

    return render(request, "registration/register.html", {
        'form': form,
        'registration': registration,
        'subscribe_plan': subscribe_plan,
        'reg_coupon': reg_coupon,
    })


def sudo_login(request):
    from django.contrib.auth.views import login as login_view

    target_user = None
    if request.session.get('sudo_user'):
        target_user = User.objects.get(id=request.session['sudo_user'])

    return login_view(
        request,
        authentication_form=EmailAuthenticationForm,
        extra_context={
            'target_user': target_user
        }
    )


@require_http_methods(['GET'])
@login_required
def user_profile_invoices(request):
    if request.is_ajax() and request.user.have_stripe_billing():
        invoices = get_stripe_invoice_list(request.user.stripe_customer)
        return render(request, 'payments/invoice_table.html', {'invoices': invoices})
    raise Http404


@login_required
def user_invoices(request, invoice_id):
    if not request.user.have_stripe_billing():
        raise Http404

    invoice = get_stripe_invoice(invoice_id, expand=['charge'])

    if not invoice:
        raise Http404
    if not invoice.customer == request.user.stripe_customer.customer_id:
        raise Http404

    return render(request, 'user/invoice_view.html', {'invoice': invoice})


@login_required
def user_invoices_download(request, invoice_id):
    from stripe_subscription.invoices.pdf import draw_pdf

    if not request.user.have_stripe_billing():
        raise Http404

    invoice = get_stripe_invoice(invoice_id, expand=['charge'])

    if not invoice:
        raise Http404
    if not invoice.customer == request.user.stripe_customer.customer_id:
        raise Http404

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="%s.pdf"' % invoice.id
    buffer = BytesIO()  # Output buffer
    draw_pdf(buffer, invoice)
    response.write(buffer.getvalue())
    buffer.close()

    return response


def crossdomain(request):
    html = """
        <cross-domain-policy>
            <allow-access-from domain="*.pixlr.com"/>
            <site-control permitted-cross-domain-policies="master-only"/>
            <allow-http-request-headers-from domain="*.pixlr.com" headers="*" secure="true"/>
        </cross-domain-policy>
    """
    return HttpResponse(html, content_type='application/xml')


def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type='text/plain')


def handler404(request):
    response = render_to_response('404.html', {},
                                  context_instance=RequestContext(request))
    response.status_code = 404
    return response


def handler500(request):
    response = render_to_response('500.html', {},
                                  context_instance=RequestContext(request))
    response.status_code = 500
    return response
