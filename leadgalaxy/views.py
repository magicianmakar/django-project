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
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.core.exceptions import PermissionDenied
from django.core.signing import Signer
from django.db import transaction
from django.db.models import Count, Max, F
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.http import JsonResponse
from django.shortcuts import redirect
from django.shortcuts import render, get_object_or_404, render_to_response
from django.template import RequestContext
from django.template.defaultfilters import truncatewords
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from unidecode import unidecode
from raven.contrib.django.raven_compat.models import client as raven_client
import keen

from analytic_events.models import RegistrationEvent

from shopified_core import permissions
from shopified_core.utils import send_email_from_template, version_compare, get_mimetype
from shopified_core.paginators import SimplePaginator
from shopified_core.shipping_helper import load_uk_provincess, missing_province, get_counrties_list

from shopify_orders import utils as shopify_orders_utils
from shopify_orders.models import (
    ShopifyOrder,
    ShopifySyncStatus,
    ShopifyOrderShippingLine,
)

from stripe_subscription.utils import (
    process_webhook_event,
    sync_subscription,
    get_stripe_invoice,
    get_stripe_invoice_list,
)

import tasks
import utils
from .forms import *
from .models import *
from .templatetags.template_helper import money_format


@login_required
def index_view(request):
    stores = request.user.profile.get_shopify_stores()
    config = request.user.models_user.profile.get_config()

    first_visit = config.get('_first_visit', True)

    if first_visit:
        request.user.set_config('_first_visit', False)

    if request.user.profile.plan.slug == 'jvzoo-free-gift':
        first_visit = False

    can_add, total_allowed, user_count = permissions.can_add_store(request.user)

    extra_stores = can_add and request.user.profile.plan.is_stripe() and \
        request.user.profile.get_shopify_stores().count() >= 1 and \
        total_allowed != -1

    templates = DescriptionTemplate.objects.filter(user=request.user).defer('description')
    markup_rules = PriceMarkupRule.objects.filter(user=request.user)

    return render(request, 'index.html', {
        'stores': stores,
        'config': config,
        'first_visit': first_visit or request.GET.get('new'),
        'extra_stores': extra_stores,
        'templates': templates,
        'markup_rules': markup_rules,
        'marktup_types': PRICE_MARKUP_TYPES,
        'page': 'index',
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
                store = ShopifyStore.objects.get(id=request.GET['store'])
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
                product.price_notification_id = 0
                product.shopify_id = 0

                try:
                    images = json.load(product.get_original_data()).get('images')
                    if images:
                        product.update_data({'images': images})
                except:
                    pass

                product.save()

                AliexpressProductChange.objects.filter(product=product).delete()

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

                cache.delete(make_template_fragment_key('orders_status', [store.id]))

                if not new_order and cache.get('active_order_{}'.format(shopify_order['id'])):
                    order_note = shopify_order.get('note')
                    if not order_note:
                        order_note = ''

                    store.pusher_trigger('order-note-update', {
                        'order_id': shopify_order['id'],
                        'note': order_note,
                        'note_snippet': truncatewords(order_note, 10),
                    })

                return JsonResponse({'status': 'ok'})

            elif topic == 'orders/delete':
                shopify_orders_utils.delete_shopify_order(store, shopify_order)
                return JsonResponse({'status': 'ok'})

            elif topic == 'shop/update':
                if shop_data.get('name'):
                    store.title = shop_data.get('name')
                    store.currency_format = shop_data.get('money_in_emails_format')
                    store.save()

                    return JsonResponse({'status': 'ok'})

            elif topic == 'app/uninstalled':
                store.is_active = False
                store.uninstalled_at = timezone.now()
                store.save()

                utils.detach_webhooks(store, delete_too=True)

                return JsonResponse({'status': 'ok'})
            else:
                raise Exception('WEBHOOK: options not found: {}'.format(topic))
        except:
            raven_client.captureException()

            return JsonResponse({'status': 'ok', 'warning': 'Processing exception'})

    elif provider == 'price-notification' and request.method == 'POST':
        product_id = request.GET['product']
        try:
            product = ShopifyProduct.objects.get(id=product_id)
            shopify_product = utils.get_shopify_product(
                product.store,
                product.get_shopify_id(),
                raise_for_status=True
            )

            cache.set('alert_product_{}'.format(product.id), shopify_product)

        except ShopifyProduct.DoesNotExist:
            return JsonResponse({'error': 'Product Not Found'}, status=404)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [401, 402, 403, 404]:
                product.price_notification_id = -4
                product.save()

                return JsonResponse({'error': 'Product Not Found'}, status=404)
            else:
                raven_client.captureException(leve='warning')

        if product.user.can('price_changes.use') and product.is_connected():
            product_change = AliexpressProductChange.objects.create(
                product=product,
                user=product.user,
                data=request.body
            )

            tasks.product_change_alert.delay(product_change.pk)
        else:
            product.price_notification_id = 0
            product.save()

            return JsonResponse({'error': 'User do not have Alerts permission'}, status=404)

        return JsonResponse({'status': 'ok'})

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
    else:
        return JsonResponse({'status': 'ok', 'warning': 'Unknown provider'})


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

    if sort:
        if re.match(r'^-?(title|price)$', sort):
            res = res.order_by(sort)

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
        res = res.filter(title__icontains=fdata.get('title'))

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
        res = res.filter(tag__icontains=fdata.get('tag'))

    if fdata.get('vendor'):
        res = res.filter(default_supplier__supplier_name__icontains=fdata.get('vendor'))

    return res


@login_required
def products_list(request, tpl='grid'):
    store = request.GET.get('store', 'n')

    args = {
        'request': request,
        'filter_products': (request.GET.get('f') == '1'),
        'post_per_page': utils.safeInt(request.GET.get('ppp'), 24),
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

    if not product.store:
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

    shopify_product = None
    if product.shopify_id and product.store:
        p['shopify_url'] = product.store.get_link('/admin/products/{}'.format(product.shopify_id))
        p['variant_edit'] = '/product/variants/{}/{}'.format(product.store.id, product.shopify_id)

        shopify_product = utils.get_shopify_product(product.store, product.shopify_id)

        if shopify_product:
            shopify_product = utils.link_product_images(shopify_product)

            p['product']['description'] = shopify_product['body_html']
            p['product']['published'] = shopify_product['published_at'] is not None

            if arrow.get(shopify_product['updated_at']).datetime > p['qelem'].updated_at or request.GET.get('sync'):
                tasks.update_shopify_product(
                    product.store.id,
                    product.shopify_id,
                    shopify_product=shopify_product,
                    product_id=p['qelem'].id)

    breadcrumbs = [{'title': 'Products', 'url': '/product'}]

    if product.store_id:
        breadcrumbs.append({'title': product.store.title, 'url': '/product?store={}'.format(product.store.id)})

    breadcrumbs.append(p['product']['title'])

    return render(request, 'product_view.html', {
        'product': p,
        'board': board,
        'original': original,
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
        v['image'] = images.get(v['id']) or shopify_product.get('image', {}).get('src')
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
            'post_per_page': utils.safeInt(request.GET.get('ppp'), 25),
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
            fields='id,title,product_type,image,variants')

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

    boards = request.user.models_user.shopifyboard_set.all()

    return render(request, 'boards_list.html', {
        'boards': boards,
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
        'post_per_page': utils.safeInt(request.GET.get('ppp'), 25),
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

    aliexpress_id = request.GET.get('id')
    product = request.GET.get('product')
    supplier = request.GET.get('supplier')

    country_code = request.GET.get('country', 'US')
    if country_code == 'GB':
        country_code = 'UK'
    elif country_code == 'ME':
        country_code = 'MNE'

    if not aliexpress_id and supplier:
        if not request.GET.get('chq'):
            if int(supplier) == 0:
                product = ShopifyProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = ProductSupplier.objects.get(id=supplier)
        else:
            if int(supplier) == 0:
                product = CommerceHQProduct.objects.get(id=product)
                permissions.user_can_view(request.user, product)
                supplier = product.default_supplier
            else:
                supplier = CommerceHQSupplier.objects.get(id=supplier)

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

    if not request.user.is_authenticated():
        return HttpResponseRedirect('%s?%s' % (reverse('django.contrib.auth.views.login'),
                                               urllib.urlencode({'next': request.get_full_path()})))

    if request.GET.get('chq'):
        product = get_object_or_404(CommerceHQProduct, id=request.GET.get('product'))
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
        'info': shippement_data,
        'store': store
    })


@login_required
def acp_users_list(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    random_cache = 0
    q = request.GET.get('q')

    if q or cache.get('template.cache.acp_users.invalidate'):
        random_cache = arrow.now().timestamp

    users = User.objects.select_related('profile', 'profile__plan').order_by('-date_joined')

    if request.GET.get('plan', None):
        users = users.filter(profile__plan_id=request.GET.get('plan'))

    if q:
        qid = utils.safeInt(q)
        if qid:
            users = users.filter(
                Q(shopifystore__id=qid)
            )
        else:
            users = users.filter(
                Q(username__icontains=q) |
                Q(email__icontains=q) |
                Q(profile__emails__icontains=q) |
                Q(profile__ips__icontains=q) |
                Q(shopifystore__title__icontains=q)
            )
        users = users.distinct()

    plans = GroupPlan.objects.all()
    bundles = FeatureBundle.objects.all()
    profiles = UserProfile.objects.all()

    if q:
        profiles = profiles.filter(user__in=users)

    return render(request, 'acp/users_list.html', {
        'users': users,
        'plans': plans,
        'bundles': bundles,
        'profiles': profiles,
        'users_count': users.count(),
        'random_cache': random_cache,
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

    if graph_type == 'tracking':
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

    data.stores_count = ShopifyStore.objects.count()
    data.products_count = (ShopifyProduct.objects.filter(user=user) if user else ShopifyProduct.objects.all()).count()
    data.users_count = User.objects.all().count()

    if graph_type == 'tracking':
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
    if not request.user.is_authenticated():
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
        products = request.user.models_user.shopifyproduct_set.only('id', 'title', 'data').filter(title__icontains=q, shopify_id__gt=0)
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
                                                           .filter(title__icontains=q) \
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
                shopify_product['variants'][i]['image'] = images.get(v['id']) or shopify_product.get('image', {}).get('src')

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

    if not request.user.is_subuser and stripe_customer:
        sync_subscription(request.user)

    return render(request, 'user/profile.html', {
        'countries': get_counrties_list(),
        'now': timezone.now(),
        'extra_bundles': extra_bundles,
        'bundles': bundles,
        'stripe_plans': stripe_plans,
        'stripe_customer': stripe_customer,
        'clippingmagic_plans': clippingmagic_plans,
        'clippingmagic': clippingmagic,
        'captchacredit_plans': captchacredit_plans,
        'captchacredit': captchacredit,
        'page': 'user_profile',
        'breadcrumbs': ['Profile']
    })


def user_unlock(request, token):
    data = cache.get('unlock_account_{}'.format(token))
    if data is None:
        raise Http404('Token Not Found')

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

    if not utils.upload_from_url(img_url, request.user.profile.import_stores()):
        raven_client.captureMessage('Upload from URL', level='warning', extra={'url': img_url})

    fp = StringIO.StringIO(requests.get(img_url).content)
    return HttpResponse(fp, content_type=get_mimetype(img_url))


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

        fp = image

    elif 'clippingmagic' in request.POST:
        if not request.user.can('clippingmagic.use'):
            return render(request, 'upgrade.html')

        product_id = request.POST.get('product')
        img_url = request.POST.get('url')
        fp = StringIO.StringIO(requests.get(img_url).content)
        img_url = '%s.png' % img_url

    else:
        # Aviary
        if not request.user.can('aviary_photo_editor.use'):
            return render(request, 'upgrade.html')

        product_id = request.POST.get('product')
        img_url = request.POST.get('url')

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

    chq_product = request.GET.get('chq') or request.POST.get('chq')
    if not chq_product:
        product = ShopifyProduct.objects.get(id=product_id)
        permissions.user_can_edit(request.user, product)
        UserUpload.objects.create(user=request.user.models_user, product=product, url=upload_url[:510])
    else:
        from commercehq_core.models import CommerceHQProduct, CommerceHQUserUpload

        product = CommerceHQProduct.objects.get(id=product_id)
        permissions.user_can_edit(request.user, product)
        CommerceHQUserUpload.objects.create(user=request.user.models_user, product=product, url=upload_url[:510])

    # For Pixlr upload, trigger the close of the editor
    if 'advanced' in request.GET:
        product.store.pusher_trigger('pixlr-editor', {
            'success': True,
            'product': product_id,
            'url': upload_url
        })

    return JsonResponse({
        'status': 'ok',
        'url': upload_url
    })


@login_required
def orders_view(request):
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
    order_custom_line_attr = bool(request.user.get_config('order_custom_line_attr'))

    if user_version and latest_release \
            and version_compare(user_version, latest_release) < 0 \
            and cache.get('extension_required', False):
        messages.warning(
            request, 'You are using version <b>{}</b> of the extension, the latest version is <b>{}.</b> '
            '<a href="/pages/13">View Upgrade Instructions</a>'.format(user_version, latest_release))

    sort = utils.get_orders_filter(request, 'sort', 'desc')
    status = utils.get_orders_filter(request, 'status', 'open')
    fulfillment = utils.get_orders_filter(request, 'fulfillment', 'unshipped,partial')
    financial = utils.get_orders_filter(request, 'financial', 'paid,partially_refunded')
    sort_field = utils.get_orders_filter(request, 'sort', 'created_at')
    sort_type = utils.get_orders_filter(request, 'desc', checkbox=True)
    connected_only = utils.get_orders_filter(request, 'connected', checkbox=True)
    awaiting_order = utils.get_orders_filter(request, 'awaiting_order', checkbox=True)

    query = request.GET.get('query') or request.GET.get('id')
    query_order = request.GET.get('query_order') or request.GET.get('id')
    query_customer = request.GET.get('query_customer')
    query_address = request.GET.getlist('query_address')

    product_filter = request.GET.getlist('product')
    supplier_filter = request.GET.get('supplier_name')
    shipping_method_filter = request.GET.get('shipping_method_name')

    if request.GET.get('shop') or query or query_order:
        status, fulfillment, financial = ['any', 'any', 'any']
        connected_only = False
        awaiting_order = False

    if request.GET.get('old') == '1':
        shopify_orders_utils.disable_store_sync(store)
    elif request.GET.get('old') == '0':
        shopify_orders_utils.enable_store_sync(store)

    created_at_start, created_at_end = None, None
    created_at_daterange = request.GET.get('created_at_daterange')
    if created_at_daterange:
        try:
            tz = timezone.localtime(timezone.now()).strftime(' %z')

            created_at_start, created_at_end = [arrow.get(d + tz, r'MM/DD/YYYY Z') for d in created_at_daterange.split('-')]
            created_at_end = created_at_end.span('day')[1]
            created_at_start, created_at_end = created_at_start.datetime, created_at_end.datetime
        except:
            created_at_daterange = None

    store_order_synced = shopify_orders_utils.is_store_synced(store)
    store_sync_enabled = store_order_synced and (shopify_orders_utils.is_store_sync_enabled(store) or request.GET.get('new'))
    support_product_filter = shopify_orders_utils.support_product_filter(store) and models_user.can('exclude_products.use')

    if not store_sync_enabled:
        if ',' in fulfillment:
            # Direct API call doesn't support more that one fulfillment status
            fulfillment = 'unshipped'

        if created_at_start and created_at_end:
            created_at_start, created_at_end = arrow.get(created_at_start).isoformat(), arrow.get(created_at_end).isoformat()

        open_orders = store.get_orders_count(status, fulfillment, financial,
                                             query=utils.safeInt(query, query),
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
        paginator.set_reverse_order(sort == 'desc')
        paginator.set_query(utils.safeInt(query, query))

        page = min(max(1, page), paginator.num_pages)
        current_page = paginator.page(page)
        page = current_page
    else:
        orders = ShopifyOrder.objects.filter(store=store)

        if ShopifySyncStatus.objects.get(store=store).sync_status == 6:
            messages.info(request, 'Your Store Orders are being imported')
        else:
            orders_sync_check_key = 'store_orders_sync_check_{}'.format(store.id)
            if cache.get(orders_sync_check_key) is None:
                shopify_count = store.get_orders_count(all_orders=True)
                db_count = orders.count()
                if shopify_count > db_count:
                    tasks.sync_shopify_orders.apply_async(args=[store.id])

                    raven_client.captureMessage('Sync Store Orders', level='info', extra={
                        'store': store.title,
                        'missing': (shopify_count - db_count)
                    })

                    messages.info(request, '<i class="fa fa-circle-o-notch fa-spin"></i> Importing {} orders from your store'
                                           '<span class="order_sync_status"> (0%)</span>'.format(shopify_count - db_count))

                cache.set(orders_sync_check_key, True, timeout=43200)

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

        if query_customer:
            orders = orders.filter(Q(customer_name__icontains=query_customer) |
                                   Q(customer_email__iexact=query_customer))

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
            orders = orders.order_by(sort_desc + sort_field.replace('created_at', 'order_id'))

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
                if arrow.get(order['updated_at']).timestamp > order['db_updated_at'] and not settings.DEBUG:
                    tasks.update_shopify_order.apply_async(
                        args=[store.id, order['id']],
                        kwarg={'shopify_order': order, 'from_webhook': False},
                        countdown=countdown)

                    countdown = countdown + 1
        else:
            page = []

    products_cache = {}
    auto_orders = request.user.can('auto_order.use')
    uk_provinces = None

    orders_cache = {}
    orders_ids = []
    products_ids = []
    for order in page:
        orders_ids.append(order['id'])
        for line in order['line_items']:
            line_id = line.get('product_id')
            products_ids.append(line_id)

    orders_list = {}
    res = ShopifyOrderTrack.objects.filter(store=store, order_id__in=orders_ids).defer('data')
    for i in res:
        orders_list['{}-{}'.format(i.order_id, i.line_id)] = i

    images_list = {}
    res = ShopifyProductImage.objects.filter(store=store, product__in=products_ids)
    for i in res:
        images_list['{}-{}'.format(i.product, i.variant)] = i.image

    for index, order in enumerate(page):
        created_at = arrow.get(order['created_at'])
        try:
            created_at = created_at.to(request.session['django_timezone'])
        except:
            raven_client.captureException(level='warning')

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

        if type(order['refunds']) is list:
            for refund in order['refunds']:
                for refund_line in refund['refund_line_items']:
                    order['refunded_lines'].append(refund_line['line_item_id'])

        for i, el in enumerate((order['line_items'])):
            var_link = store.get_link('/admin/products/{}/variants/{}'.format(el['product_id'],
                                                                              el['variant_id']))
            order['line_items'][i]['variant_link'] = var_link
            order['line_items'][i]['refunded'] = el['id'] in order['refunded_lines']

            order['line_items'][i]['image'] = {
                'store': store.id,
                'product': el['product_id'],
                'variant': el['variant_id']
            }

            order['line_items'][i]['image_src'] = images_list.get('{}-{}'.format(el['product_id'], el['variant_id']))

            shopify_order = orders_list.get('{}-{}'.format(order['id'], el['id']))
            order['line_items'][i]['shopify_order'] = shopify_order

            variant_id = el['variant_id']
            if not el['product_id']:
                if variant_id:
                    product = ShopifyProduct.objects.filter(store=store, title=el['title'], shopify_id__gt=0).first()
                else:
                    product = None
            elif el['product_id'] in products_cache:
                product = products_cache[el['product_id']]
            else:
                product = ShopifyProduct.objects.filter(store=store, shopify_id=el['product_id']).first()

            if shopify_order or el['fulfillment_status'] == 'fulfilled' or (product and product.is_excluded):
                order['placed_orders'] += 1

            country_code = order.get('shipping_address', {}).get('country_code')
            if not country_code:
                country_code = order.get('customer', {}).get('default_address', {}).get('country_code')

            supplier = None
            bundle_data = []
            if product and product.have_supplier():
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

                bundles = product.get_bundle_mapping(variant_id)
                if bundles:
                    product_bundles = []
                    for idx, b in enumerate(bundles):
                        b_product = ShopifyProduct.objects.get(id=b['id'])
                        b_variant_id = b_product.get_real_variant_id(b['variant_id'])
                        b_supplier = b_product.get_suppier_for_variant(variant_id)
                        if b_supplier:
                            b_shipping_method = b_product.get_shipping_for_variant(
                                supplier_id=b_supplier.id,
                                variant_id=b_variant_id,
                                country_code=country_code)
                        else:
                            b_shipping_method = None

                        b_variant_mapping = b_product.get_variant_mapping(name=b_variant_id, for_extension=True, mapping_supplier=True)
                        if variant_id and b_variant_mapping:
                            b_variants = b_variant_mapping
                        else:
                            b_variants = b['variant_title'].split('/') if b['variant_title'] else ''

                        product_bundles.append({
                            'product': b_product,
                            'supplier': b_supplier,
                            'shipping_method': b_shipping_method,
                            'quantity': b['quantity'],
                            'data': b
                        })

                        bundle_data.append({
                            'quantity': b['quantity'],
                            'product_id': b_product.id,
                            'source_id': b_supplier.get_source_id(),
                            'variants': b_variants,
                            'shipping_method': b_shipping_method,
                            'country_code': country_code,
                        })

                    order['line_items'][i]['bundles'] = product_bundles
                    order['line_items'][i]['is_bundle'] = len(bundle_data) > 0
                    order['have_bundle'] = True

                order['connected_lines'] += 1

            products_cache[el['product_id']] = product

            if 'shipping_address' not in order \
                    and order.get('customer') and order.get('customer').get('default_address'):
                order['shipping_address'] = order['customer'].get('default_address')

            if auto_orders and 'shipping_address' in order:
                try:
                    shipping_address_asci = {}  # Aliexpress doesn't allow unicode
                    shipping_address = order['shipping_address']
                    for k in shipping_address.keys():
                        if shipping_address[k] and type(shipping_address[k]) is unicode:
                            shipping_address_asci[k] = unidecode(shipping_address[k])
                        else:
                            shipping_address_asci[k] = shipping_address[k]

                    if not shipping_address_asci[u'province']:
                        if shipping_address_asci[u'country'] == u'United Kingdom' and shipping_address_asci['city']:
                            if not uk_provinces:
                                uk_provinces = load_uk_provincess()

                            province = uk_provinces.get(shipping_address_asci[u'city'].lower().strip(), u'')
                            if not province:
                                missing_province(shipping_address_asci['city'])

                            shipping_address_asci[u'province'] = province
                        else:
                            shipping_address_asci[u'province'] = shipping_address_asci[u'country_code']

                    elif shipping_address_asci[u'province'] == 'Washington DC':
                        shipping_address_asci[u'province'] = u'Washington'

                    elif shipping_address_asci['province'] == 'Puerto Rico':
                        # Puerto Rico is a country in Aliexpress
                        shipping_address_asci['province'] = 'PR'
                        shipping_address_asci['country_code'] = 'PR'
                        shipping_address_asci['country'] = 'Puerto Rico'

                    elif shipping_address_asci['province'] == 'Virgin Islands':
                        # Virgin Islands is a country in Aliexpress
                        shipping_address_asci['province'] = 'VI'
                        shipping_address_asci['country_code'] = 'VI'
                        shipping_address_asci['country'] = 'Virgin Islands (U.S.)'

                    elif shipping_address_asci['province'] == 'Guam':
                        # Guam is a country in Aliexpress
                        shipping_address_asci['province'] = 'GU'
                        shipping_address_asci['country_code'] = 'GU'
                        shipping_address_asci['country'] = 'Guam'

                    if shipping_address_asci['country_code'] == 'CA':
                        if shipping_address_asci.get('zip'):
                            shipping_address_asci['zip'] = re.sub(r'[\n\r\t ]', '', shipping_address_asci['zip']).strip()

                        if shipping_address_asci['province'] == 'Newfoundland':
                            shipping_address_asci['province'] = 'Newfoundland and Labrador'

                    shipping_address_asci['name'] = utils.ensure_title(shipping_address_asci['name'])

                    if shipping_address_asci['company']:
                        shipping_address_asci['name'] = '{} - {}'.format(shipping_address_asci['name'],
                                                                         shipping_address_asci['company'])

                    order_data = {
                        'id': '{}_{}_{}'.format(store.id, order['id'], el['id']),
                        'quantity': el['quantity'],
                        'shipping_address': shipping_address_asci,
                        'order_id': order['id'],
                        'line_id': el['id'],
                        'product_id': product.id if product else None,
                        'source_id': supplier.get_source_id() if supplier else None,
                        'total': utils.safeFloat(el['price'], 0.0),
                        'store': store.id,
                        'order': {
                            'phone': {
                                'number': shipping_address_asci.get('phone'),
                                'country': shipping_address_asci['country_code']
                            },
                            'note': order_custom_note,
                            'epacket': epacket_shipping,
                            'auto_mark': auto_ordered_mark,  # Auto mark as Ordered
                        },
                        'products': bundle_data,
                        'is_bundle': len(bundle_data) > 0
                    }

                    if order_custom_line_attr and el.get('properties'):
                        item_note = '\n'.join(['{name}: {value}'.format(**prop) for prop in el['properties']])
                        item_note = 'Here are custom information for the ordered product:\n{}'.format(item_note)

                        order_data['order']['item_note'] = item_note
                        order['line_items'][i]['item_note'] = item_note

                    if product:
                        mapped = product.get_variant_mapping(name=variant_id, for_extension=True, mapping_supplier=True)
                        if variant_id and mapped:
                            order_data['variant'] = mapped
                        else:
                            order_data['variant'] = el['variant_title'].split('/') if el['variant_title'] else ''

                    if product and product.have_supplier():
                        orders_cache['order_{}'.format(order_data['id'])] = order_data
                        order['line_items'][i]['order_data_id'] = order_data['id']

                        order['line_items'][i]['order_data'] = order_data
                except:
                    if settings.DEBUG:
                        traceback.print_exc()

                    raven_client.captureException()

        all_orders.append(order)

    active_orders = {}
    for i in orders_ids:
        active_orders['active_order_{}'.format(i)] = True

    cache.set_many(orders_cache, timeout=3600)
    cache.set_many(active_orders, timeout=3600)

    if store_order_synced:
        countries = get_counrties_list()
    else:
        countries = []

    if product_filter:
        product_filter = models_user.shopifyproduct_set.filter(id__in=product_filter)

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
        'user_filter': utils.get_orders_filter(request),
        'store_order_synced': store_order_synced,
        'store_sync_enabled': store_sync_enabled,
        'countries': countries,
        'created_at_daterange': created_at_daterange,
        'page': 'orders',
        'breadcrumbs': breadcrumbs
    })


@login_required
def orders_track(request):
    if not request.user.can('orders.use'):
        return render(request, 'upgrade.html')

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

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Tracking page.')
        return HttpResponseRedirect('/')

    orders = ShopifyOrderTrack.objects.select_related('store').filter(user=request.user.models_user, store=store).defer('data')

    if query:
        order_id = shopify_orders_utils.order_id_from_name(store, query)

        if order_id:
            query = str(order_id)

        orders = orders.filter(Q(order_id=utils.clean_query_id(query)) |
                               Q(source_id=utils.clean_query_id(query)) |
                               Q(source_tracking__icontains=query))

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
        orders = orders.filter(source_status_details=source_reason)

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
        'paginator': paginator,
        'current_page': page,
        'page': 'orders_track',
        'breadcrumbs': [{'title': 'Orders', 'url': '/orders'}, 'Tracking']
    })


@login_required
def orders_place(request):
    try:
        assert request.GET['product']
        assert request.GET['SAPlaceOrder']

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
        elif service == 'admitad':
            redirect_url = utils.get_admitad_affiliate_url(admitad_site_id, product)

    if not redirect_url:
        redirect_url = product

    for k in request.GET.keys():
        if k.startswith('SA') and k not in redirect_url:
            redirect_url = utils.affiliate_link_set_query(redirect_url, k, request.GET[k])

    # Verify if the user didn't pass order limit
    parent_user = request.user.models_user
    plan = parent_user.profile.plan
    if plan.auto_fulfill_limit != -1:
        month_start = [i.datetime for i in arrow.utcnow().span('month')][0]
        orders_count = parent_user.shopifyordertrack_set.filter(created_at__gte=month_start).count()

        if not plan.auto_fulfill_limit or orders_count + 1 > plan.auto_fulfill_limit:
            messages.error(request, "You have reached your plan auto fulfill limit")
            return HttpResponseRedirect('/')

    # Save Auto fulfill event
    event_data = {}
    order_key = request.GET['SAPlaceOrder']
    event_key = 'keen_event_{}'.format(request.GET['SAPlaceOrder'])

    if not order_key.startswith('order_'):
        order_key = 'order_{}'.format(order_key)

    order_data = cache.get(order_key)
    prefix, store, order, line = order_key.split('_')

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
                event_data['product'] = re.findall('[/_]([0-9]+).html', request.GET[k])
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

        try:
            keen.add_event("auto_fulfill", event_data)
            cache.set(event_key, True, timeout=3600)
        except:
            raven_client.captureException(level='warning')

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

    show_hidden = 'hidden' in request.GET

    product = request.GET.get('product')
    if product:
        product = get_object_or_404(ShopifyProduct, id=product)
        permissions.user_can_view(request.user, product)

    post_per_page = utils.safeInt(request.GET.get('ppp'), 20)
    page = utils.safeInt(request.GET.get('page'), 1)

    store = utils.get_store_from_request(request)
    if not store:
        messages.warning(request, 'Please add at least one store before using the Alerts page.')
        return HttpResponseRedirect('/')

    AliexpressProductChange.objects.filter(user=request.user.models_user,
                                           product__store=None).delete()

    changes = AliexpressProductChange.objects.select_related('product') \
                                     .select_related('product__default_supplier') \
                                     .filter(user=request.user.models_user,
                                             product__store=store)

    if request.user.is_subuser:
        store_ids = request.user.profile.subuser_permissions.filter(
            codename='view_alerts'
        ).values_list(
            'store_id', flat=True
        )
        changes = changes.filter(product__store_id__in=store_ids)

    if product:
        changes = changes.filter(product=product)
    else:
        changes = changes.filter(hidden=show_hidden)

    changes = changes.order_by('-updated_at')

    paginator = SimplePaginator(changes, post_per_page)
    page = min(max(1, page), paginator.num_pages)
    page = paginator.page(page)
    changes = page.object_list

    product_changes = []
    for i in changes:
        change = {'qelem': i}
        change['id'] = i.id
        change['data'] = json.loads(i.data)
        change['changes'] = utils.product_changes_remap(change['data'])
        change['product'] = i.product
        change['shopify_link'] = i.product.shopify_link()
        change['original_link'] = i.product.get_original_info().get('url')

        product_changes.append(change)

    if not show_hidden:
        AliexpressProductChange.objects.filter(user=request.user.models_user) \
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

        if request.user.is_authenticated():
            initial = {'email': request.user.email}

        form = RegisterForm(initial=initial)

    return render(request, "bundles_bonus.html", {
        'form': form,
        'bundle': bundle
    })


@login_required
def products_collections(request, collection):
    post_per_page = request.GET.get('ppp', 25)
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
def subusers(request):
    if not request.user.can('sub_users.use'):
        return render(request, 'upgrade.html')

    if request.user.is_subuser:
        raise PermissionDenied()

    sub_users = User.objects.filter(profile__subuser_parent=request.user)
    invitation = PlanRegistration.objects.filter(sender=request.user) \
                                         .filter(Q(user__isnull=True) | Q(user__profile__subuser_parent=request.user))

    return render(request, 'subusers_manage.html', {
        'sub_users': sub_users,
        'invitation': invitation,
        'page': 'subusers',
        'breadcrumbs': ['Account', 'Sub Users']
    })


@login_required
def subusers_perms(request, user_id):
    try:
        user = User.objects.get(id=user_id, profile__subuser_parent=request.user)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except:
        return JsonResponse({'error': 'Unknown Error'}, status=500)

    if request.method == 'POST':
        form = SubUserStoresForm(request.POST,
                                 instance=user.profile,
                                 parent_user=request.user)
        if form.is_valid():
            form.save()

            messages.success(request, 'User permissions has been updated')
        else:
            messages.error(request, 'Error occurred during user permissions update')

        return HttpResponseRedirect(reverse('subusers'))

    else:
        form = SubUserStoresForm(instance=user.profile,
                                 parent_user=request.user)

    return render(request, 'subusers_perms.html', {
        'subuser': user,
        'form': form,
        'page': 'subusers',
        'breadcrumbs': ['Account', 'Sub Users']
    })


@login_required
def logout(request):
    user_logout(request)
    return redirect('/')


def register(request, registration=None, subscribe_plan=None):
    if request.user.is_authenticated() and not request.user.is_superuser:
        messages.warning(request, 'You are already logged in')
        return HttpResponseRedirect('/')

    if registration and registration.endswith('-subscribe'):
        slug = registration.replace('-subscribe', '')
        subscribe_plan = get_object_or_404(GroupPlan, slug=slug, payment_gateway='stripe')
        if not subscribe_plan.is_stripe():
            raise Http404('Not a Stripe Plan')

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

            reg_coupon = request.GET.get('cp')
            if reg_coupon:
                new_user.set_config('registration_discount', Signer().unsign(base64.decodestring(reg_coupon)))

            if subscribe_plan:
                try:
                    new_user.profile.apply_subscription(subscribe_plan)
                except:
                    raven_client.captureException()

            elif registration is None or registration.get_usage_count() is None:
                utils.apply_plan_registrations(form.cleaned_data['email'])
            else:
                utils.apply_shared_registration(new_user, registration)

            new_user = authenticate(username=form.cleaned_data['username'],
                                    password=form.cleaned_data['password1'])

            login(request, new_user)

            RegistrationEvent.objects.create(user=request.user)

            utils.wicked_report_add_user(request, new_user)

            if new_user.profile.plan.is_free:
                return HttpResponseRedirect("/user/profile?w=1#plan")
            else:
                return HttpResponseRedirect("/")

    else:
        try:
            initial = {
                'email': registration.email,
            }
        except:
            initial = {}

        form = RegisterForm(initial=initial)

    if registration and registration.email:
        form.fields['email'].widget.attrs['readonly'] = True

    return render(request, "registration/register.html", {
        'form': form,
        'registration': registration,
        'subscribe_plan': subscribe_plan
    })


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


@transaction.atomic
@login_required
def subuser_perms_edit(request, user_id):
    subuser = get_object_or_404(User, pk=user_id, profile__subuser_parent=request.user)
    global_permissions = subuser.profile.subuser_permissions.filter(store__isnull=True)
    initial = {'permissions': global_permissions, 'store': None}

    if request.method == 'POST':
        form = SubuserPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_permissions.remove(*global_permissions)
            subuser.profile.subuser_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('leadgalaxy.views.subuser_perms_edit', user_id)
    else:
        form = SubuserPermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse('subusers')},
        subuser.username,
        'Permissions',
    ]

    context = {'subuser': subuser, 'form': form, 'breadcrumbs': breadcrumbs}

    return render(request, 'subuser_perms_edit.html', context)


@transaction.atomic
@login_required
def subuser_store_permissions(request, user_id, store_id):
    store = get_object_or_404(ShopifyStore, pk=store_id, user=request.user)
    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_stores__pk=store_id)
    subuser_permissions = subuser.profile.subuser_permissions.filter(store=store)
    initial = {'permissions': subuser_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_permissions.remove(*subuser_permissions)
            subuser.profile.subuser_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('leadgalaxy.views.subuser_store_permissions', user_id, store_id)
    else:
        form = SubuserPermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse('subusers')},
        subuser.username,
        {'title': 'Permissions', 'url': reverse('subuser_perms_edit', args=(user_id,))},
        store.title,
    ]

    context = {'subuser': subuser, 'form': form, 'breadcrumbs': breadcrumbs}

    return render(request, 'subuser_store_permissions.html', context)


@transaction.atomic
@login_required
def subuser_chq_store_permissions(request, user_id, store_id):
    store = request.user.commercehqstore_set.filter(pk=store_id).first()
    if not store:
        raise Http404

    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_chq_stores__pk=store_id)

    subuser_chq_permissions = subuser.profile.subuser_chq_permissions.filter(store=store)
    initial = {'permissions': subuser_chq_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserCHQPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_chq_permissions.remove(*subuser_chq_permissions)
            subuser.profile.subuser_chq_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('leadgalaxy.views.subuser_chq_store_permissions', user_id, store_id)
    else:
        form = SubuserCHQPermissionsForm(initial=initial)

    breadcrumbs = ['Account', 'Sub Users', 'Permissions', subuser.username, store.title]
    context = {'subuser': subuser, 'form': form, 'breadcrumbs': breadcrumbs}
    return render(request, 'subuser_chq_store_permissions.html', context)


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
