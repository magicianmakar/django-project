import hmac
import random
import re
from hashlib import sha1

import arrow
import simplejson as json
import stripe
import texttable
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.core.signing import Signer
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404

from django.utils import timezone
from django.views import View

from alibaba_core import utils as alibaba_utils
from churnzero_core.utils import post_churnzero_cancellation_event
from leadgalaxy import utils, tasks
from leadgalaxy.models import (
    FeatureBundle,
    GroupPlan,
    PlanPayment,
    PlanRegistration,
    ShopifyStore,
    ShopifyProduct,
    ShopifyProductImage,
    AdminEvent,
    CaptchaCredit,
    UserProfile,
    AppPermission
)
from lib.exceptions import capture_message, capture_exception
from metrics.activecampaign import ActiveCampaignAPI
from product_alerts.models import ProductChange
from product_alerts.utils import delete_product_monitor, unmonitor_store
from profit_dashboard.models import FacebookAccess
from shopified_core.models_utils import get_product_model
from shopified_core.tasks import export_user_activity
from shopified_core.utils import send_email_from_template, safe_int, base64_encode, app_link, safe_float
from shopify_orders import utils as shopify_orders_utils
from shopify_orders.models import ShopifyOrder
from stripe_subscription.utils import process_webhook_event
from supplements.models import PLSOrder
from webhooks.utils import ShopifyWebhookMixing


def jvzoo_webhook(request, option):
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
            raise Exception(f'Unexpected HTTP Method: {request.method}')

        params = dict(iter(request.POST.items()))

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
                        capture_message('Unsupported Expire format', extra={'expire': expire})

                    expire_date = timezone.now() + timezone.timedelta(days=365)
                    data['expire_date'] = expire_date.isoformat()
                    data['expire_param'] = expire

                reg = utils.generate_plan_registration(plan, data)

                data['reg_hash'] = reg.register_hash
                data['plan_title'] = plan.title

                try:
                    user = User.objects.get(email__iexact=data['email'])
                    print('WARNING: JVZOO SALE UPGARDING: {} to {}'.format(data['email'], plan.title))
                except User.DoesNotExist:
                    user = None
                except Exception:
                    capture_exception()
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
                    User.objects.get(email__iexact=data['email']).profile.apply_registration(reg)
                except User.DoesNotExist:
                    pass

                send_email_from_template(
                    tpl='webhook_bundle_purchase.html',
                    subject='[Dropified] You Have Been Upgraded To {}'.format(bundle.title),
                    recipient=data['email'],
                    data=data)

            data.update(params)

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

            capture_message('JVZoo New Purchase',
                            extra={'name': data['fullname'], 'email': data['email'], 'trans_type': trans_type, 'payment': payment.id},
                            tags=tags, level='info')

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
                capture_message('JVZoo User Cancel/Refund',
                                extra={'name': data['fullname'], 'email': data['email'], 'trans_type': trans_type, 'payment': payment.id},
                                tags={'trans_type': trans_type}, level='info')

            return JsonResponse({'status': 'ok'})

    except Exception:
        capture_exception()
        return JsonResponse({'error': 'Server Error'}, status=500)

    return JsonResponse({'status': 'ok', 'warning': 'Unknown'})


def zaxaa_webhook(request, option):
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
        raise Exception(f'Unexpected HTTP Method: {request.method}')

    params = dict(iter(request.POST.items()))

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
                    capture_message('Unsupported Expire format', extra={'expire': expire})

                expire_date = timezone.now() + timezone.timedelta(days=365)
                data['expire_date'] = expire_date.isoformat()
                data['expire_param'] = expire

            reg = utils.generate_plan_registration(plan, data)

            data['reg_hash'] = reg.register_hash
            data['plan_title'] = plan.title

            try:
                user = User.objects.get(email__iexact=data['email'])
                print('WARNING: ZAXAA SALE UPGARDING: {} to {}'.format(data['email'], plan.title))
            except User.DoesNotExist:
                user = None
            except Exception:
                capture_exception()
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
                User.objects.get(email__iexact=data['email']).profile.apply_registration(reg)
            except User.DoesNotExist:
                pass

            send_email_from_template(
                tpl='webhook_bundle_purchase.html',
                subject='[Dropified] You Have Been Upgraded To {}'.format(bundle.title),
                recipient=data['email'],
                data=data)

        data.update(params)

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

        capture_message('Zaxaa New Purchase',
                        extra={'name': data['fullname'], 'email': data['email'], 'trans_type': trans_type, 'payment': payment.id},
                        tags=tags, level='info')

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
            capture_message('Zaxaa User Cancel/Refund',
                            extra={'name': data['fullname'], 'email': data['email'], 'trans_type': trans_type, 'payment': payment.id},
                            tags={'trans_type': trans_type},
                            level='info')

    return HttpResponse('ok')


class ShopifyProductUpdateWebhook(ShopifyWebhookMixing):
    def process_webhook(self, store, shopify_data):
        try:
            product = self.get_product()
        except ShopifyProduct.DoesNotExist:
            return HttpResponse('ok')

        cache.set(f'webhook_product_{store.id}_{product.shopify_id}', shopify_data, timeout=600)

        countdown_key = f'eta_product_{store.id}_{product.shopify_id}'
        if cache.get(countdown_key) is None:
            cache.set(countdown_key, True, timeout=5)
            tasks.update_shopify_product.apply_async(args=[store.id, product.shopify_id], countdown=5)


class ShopifyProductDeleteWebhook(ShopifyWebhookMixing):
    def process_webhook(self, store, shopify_data):
        try:
            product = self.get_product()
        except ShopifyProduct.DoesNotExist:
            return HttpResponse('ok')

        # Remove from Price Monitor Service
        if product.monitor_id and product.monitor_id > 0:
            try:
                delete_product_monitor(product.monitor_id)
            except:
                pass

        product.monitor_id = 0
        product.shopify_id = 0

        try:
            images = json.load(product.get_original_data()).get('images')
            if images:
                product.update_data({'images': images})
        except:
            pass

        product.save()

        ProductChange.objects.filter(shopify_product=product).delete()

        ShopifyProductImage.objects.filter(store=store, product=product.shopify_id).delete()


class ShopifyOrderCreateWebhook(ShopifyWebhookMixing):
    def process_webhook(self, store, shopify_data):
        cache.set(f'saved_orders_clear_{store.id}', True, timeout=300)

        queue = 'priority_high'
        countdown = 1

        cache.set(f'webhook_order_{store.id}_{shopify_data["id"]}', shopify_data, timeout=600)
        countdown_key = f'eta_order__{store.id}_{shopify_data["id"]}_create'
        countdown_saved = cache.get(countdown_key)
        if countdown_saved is None:
            cache.set(countdown_key, countdown, timeout=countdown * 2)
        else:
            countdown = countdown_saved + random.randint(2, 5)
            cache.set(countdown_key, countdown, timeout=countdown * 2)

        tasks.update_shopify_order.apply_async(
            args=[store.id, shopify_data['id']],
            queue=queue,
            countdown=countdown)

        cache.delete(make_template_fragment_key('orders_status', [store.id]))

        return JsonResponse({'status': 'ok'})


class ShopifyOrderUpdateWebhook(ShopifyWebhookMixing):
    def process_webhook(self, store, shopify_data):
        cache.set(f'saved_orders_clear_{store.id}', True, timeout=300)

        queue = 'celery'
        countdown = random.randint(2, 9)

        cache.set(f'webhook_order_{store.id}_{shopify_data["id"]}', shopify_data, timeout=600)
        countdown_key = f'eta_order__{store.id}_{shopify_data["id"]}_updated'
        countdown_saved = cache.get(countdown_key)
        if countdown_saved is None:
            cache.set(countdown_key, countdown, timeout=countdown * 2)
        else:
            countdown = countdown_saved + random.randint(2, 5)
            cache.set(countdown_key, countdown, timeout=countdown * 2)

        tasks.update_shopify_order.apply_async(
            args=[store.id, shopify_data['id']],
            queue=queue,
            countdown=countdown)

        cache.delete(make_template_fragment_key('orders_status', [store.id]))

        return JsonResponse({'status': 'ok'})


class ShopifyOrderDeleteWebhook(ShopifyWebhookMixing):
    def process_webhook(self, store, shopify_data):
        cache.set(f'saved_orders_clear_{store.id}', True, timeout=300)

        ShopifyOrder.objects.filter(store=store, order_id=shopify_data['id']).delete()


class ShopifyShopUpdateWebhook(ShopifyWebhookMixing):
    def process_webhook(self, store, shopify_data):
        if shopify_data.get('name'):
            store.title = shopify_data.get('name')
            store.currency_format = shopify_data.get('money_in_emails_format')
            store.refresh_info(info=shopify_data, commit=False)
            store.save()

            if store.user.profile.from_shopify_app_store() and shopify_data.get('email'):
                store.user.email = shopify_data.get('email')
                store.user.save()


class ShopifyAppUninstallWebhook(ShopifyWebhookMixing):
    def process_webhook(self, store, shopify_data):
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

        if store.user.models_user.profile.has_churnzero_account:
            post_churnzero_cancellation_event(store.user)


class ShopifyGDPRDeleteCustomerWebhook(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except:
            data = None

        if data:
            for store in ShopifyStore.objects.filter(shop=data.get('shop_domain'), is_active=False):
                try:
                    utils.verify_shopify_webhook(store, request)
                except:
                    capture_exception(level='warning')
                    continue

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

        return HttpResponse('ok')


class ShopifyGDPRDeleteStoreWebhook(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except:
            data = None

        if data:
            for store in ShopifyStore.objects.filter(shop=data.get('shop_domain'), is_active=False):
                try:
                    utils.verify_shopify_webhook(store, request)
                except:
                    capture_exception(level='warning')
                    continue

                if not store.is_active:
                    store.delete_request_at = timezone.now()
                    store.save()

        return HttpResponse('ok')


def stripe_webhook(request):
    try:
        event = json.loads(request.body)

        return process_webhook_event(request, event['id'])
    except:
        capture_exception()
        return HttpResponse('Server Error', status=500)


def clickfunnels_register(request, funnel_id, funnel_step_id, plan_id):
    try:
        data = json.loads(request.body)

        email = data['email']
        fullname = data['name']

        if funnel_id != int(data['funnel_id']) or funnel_step_id != int(data['funnel_step_id']):
            return HttpResponse('Ignore Webhook')

        plan = GroupPlan.objects.get(id=plan_id)

        user, created = utils.register_new_user(email, fullname)

        if created:
            user.profile.change_plan(plan)

            capture_message(
                'Clickfunnels Registration',
                level='warning',
                extra={
                    'name': fullname,
                    'email': email,
                    'exists': User.objects.filter(email__iexact=email).exists()
                })

            return HttpResponse('ok')
        else:
            capture_message('Clickfunnels registration email exists', extra={
                'name': fullname,
                'email': email,
                'exists': User.objects.filter(email__iexact=email).exists()
            })

            return HttpResponse('Email is already registed to an other user')

    except:
        capture_exception()

    return HttpResponse('OK')


def clickfunnels_checklogin(request):
    try:
        email = request.GET.get('email')
        if email:
            try:
                user = User.objects.get(email__iexact=email)
                data = {'user': {'email': user.email, "is_stripe": user.profile.plan.is_stripe(), "is_subuser": user.is_subuser}}
            except User.DoesNotExist:
                data = {'user': False}
        else:
            data = {'user': False}

        if 'callback' in request.GET:
            # a jsonp response!
            data = '%s(%s);' % (request.GET['callback'], json.dumps(data))
            return HttpResponse(data, "text/javascript")
        else:
            return HttpResponse({}, "text/javascript")
    except:
        capture_exception()
        return HttpResponse({}, "text/javascript")


def price_monitor_webhook(request):
    product_id = request.GET['product']
    dropified_type = request.GET['dropified_type']

    try:
        product = get_product_model(dropified_type).objects.get(id=product_id)
    except ObjectDoesNotExist:
        return JsonResponse({'error': 'Product Not Found'}, status=404)

    monitor_id = request.GET.get('monitor_id')
    if monitor_id and product.monitor_id != safe_int(monitor_id):
        return JsonResponse({'error': 'Not Registered Monitor ID'}, status=404)

    if product.user.can('price_changes.use') and product.is_connected and product.store.is_active:
        data = json.loads(request.body.decode())

        product_change = ProductChange.objects.create(
            store_type=dropified_type,
            shopify_product=product if dropified_type == 'shopify' else None,
            chq_product=product if dropified_type == 'chq' else None,
            gkart_product=product if dropified_type == 'gkart' else None,
            woo_product=product if dropified_type == 'woo' else None,
            bigcommerce_product=product if dropified_type == 'bigcommerce' else None,
            user=product.user,
            data=json.dumps(data),
        )

        countdown = random.randint(1, 120)
        tasks.manage_product_change.apply_async(
            args=[product_change.pk],
            countdown=countdown,
            expires=countdown + 900)

    else:
        product.monitor_id = 0
        product.save()
        return JsonResponse({'error': 'User do not have Alerts permission'}, status=404)

    return JsonResponse({'status': 'ok'})


def slack_webhook(request):
    request_from = None
    for user in User.objects.filter(is_staff=True):
        if request.POST['user_id'] in user.get_config('_slack_id', ''):
            request_from = user
            break

    try:
        assert request_from, 'Slack Support Staff Check'
    except:
        if not settings.DEBUG:
            capture_exception()
            return HttpResponse(':octagonal_sign: _Dropified Support Staff Only (ID: {})_'.format(request.POST['user_id']))

    if request.POST['command'] == '/store-transfer':
        try:
            text = re.split(' +', request.POST['text'])
            options = {
                'store': text[0],
                'from': text[1],
                'to': text[2],
                'response_url': request.POST['response_url'],
            }

        except:
            return HttpResponse(":x: Invalid Command Format")

        try:
            from_user = User.objects.get(id=options['from']) if safe_int(options['from']) else User.objects.get(email__iexact=options['from'])
        except:
            return HttpResponse(":x: {} user not found".format(options['from']))

        try:
            to_user = User.objects.get(id=options['to']) if safe_int(options['to']) else User.objects.get(email__iexact=options['to'])
        except:
            return HttpResponse(":x: {} user not found".format(options['to']))

        shop = re.findall(r'[^/@\.]+\.myshopify\.com', options['store'])
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

    elif request.POST['command'] == '/user-activity':
        user_id = request.POST['text']
        if not user_id:
            return HttpResponse(':x: You must specify a user email or ID')

        if user_id != 'sync':
            user = None
            try:
                user = User.objects.get(id=int(user_id))
            except ValueError:
                pass

            if not user:
                try:
                    user = User.objects.get(email__iexact=user_id)
                except:
                    return HttpResponse(f':x: User not found: {user_id}')

            export_user_activity.delay(user.id, request_from.id)

            return HttpResponse(f':hourglass: Exporting activty for *{user.email}*')
        else:
            export_user_activity.delay(user_id, request_from.id)
            return HttpResponse(':hourglass: Starting user activity syncing')

    elif request.POST['command'] == '/captcha-credit':
        is_review_bonus = False
        args = request.POST['text'].split(' ')
        if len(args) == 2:
            email = args[0]
            credits_count = args[1]
            if credits_count == 'review':
                credits_count = 1000
                is_review_bonus = True
        elif len(args) == 1:
            email = args[0]
            credits_count = 1000
        else:
            return HttpResponse(':x: Number of arguments is not correct {}'.format(request.POST['text']))

        user = User.objects.get(email=email)

        if is_review_bonus and user.can('aliexpress_captcha.use'):
            user.set_config('_double_orders_limit', arrow.utcnow().timestamp)
            return HttpResponse('{} Double Orders Limit for *{}*'.format(credits_count, email))

        try:
            captchacredit = CaptchaCredit.objects.get(user=user)
            captchacredit.remaining_credits += safe_int(credits_count, 0)
            captchacredit.save()

        except CaptchaCredit.DoesNotExist:
            CaptchaCredit.objects.create(
                user=user,
                remaining_credits=credits_count
            )

        return HttpResponse('{} Captcha Credits added to *{}*'.format(credits_count, email))

    elif request.POST['command'] == '/dash-facebook-reset':
        args = request.POST['text'].split(' ')
        access = FacebookAccess.objects

        shop = None
        if len(args) >= 2:
            shop = re.findall(r'[^/@\.]+\.myshopify\.com', args[1])
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
        return HttpResponse("Deleted {} Facebook Synced Accounts".format(models.get('profit_dashboard.FacebookAccess', 0)))

    elif request.POST['command'] == '/dash-facebook-list':
        access_list = FacebookAccess.objects.select_related('store').filter(user__email=request.POST['text'])
        result = []
        for access in access_list:
            accounts = ', '.join([a.account_name for a in access.accounts.all()])
            result.append('Store: {} | Facebook: {} | Accounts: {}'.format(
                access.store.shop,
                access.facebook_user_id,
                accounts
            ))

        return HttpResponse('Results:\n{}'.format('\n'.join(result if result else ['Not found'])))

    elif request.POST['command'] == '/user-tags':
        # Available Commands:
        # /user-tags <add|remove|set> <email> <tags>
        # /user-tags <search> <tags>
        # :tags param example: Added Product, Connected Store, Multiple Stores

        args = request.POST['text'].split(' ')
        command = args[0]

        if command == 'search':
            tags = ' '.join(args[1:])
            profiles = UserProfile.objects.filter(tags__icontains=tags)

            result = []
            for profile in profiles:
                result.append('{}|{}|{}'.format(
                    profile.user.email,
                    profile.user.get_full_name(),
                    profile.tags
                ))

            return HttpResponse('Results:\n{}'.format('\n'.join(result if result else ['Not found'])))
        else:
            try:
                profile = UserProfile.objects.get(user__email__iexact=args[1])

            except UserProfile.DoesNotExist:
                profile = UserProfile.objects.filter(user_id=args[1])
                if profile.exists():
                    profile = profile.first()
                else:
                    return HttpResponse(':x: Profile not found')

            except UserProfile.MultipleObjectsReturned:
                profiles = UserProfile.objects.filter(user__email__iexact=args[1])
                return HttpResponse(':x: More than one account with the same email was found, '
                                    + 'Use one of the following User IDs instead:\n{}'.format(
                                        '\n'.join([f'{profile.user.id} - {profile.user.username}' for profile in profiles])))

            tags = ' '.join(args[2:]).split(',')
            if command == 'add':
                profile.add_tags(tags)
                result = 'Tags Added'

            elif command == 'set':
                profile.set_tags(tags)
                result = 'Tag Set'

            elif command == 'remove':
                profile.remove_tags(tags)
                result = 'Tags Removed'

            else:
                result = ':x: Unknown Command: {}'.format(command)

            return HttpResponse(result)

    elif request.POST['command'] == '/permission':
        args = request.POST['text'].split(' ')
        command = args[0]

        if command == 'create':
            if len(args) < 3:
                return HttpResponse(':x: Wrong number of arguments')

            name = args[1]
            if '.' in name:
                parts = name.split('.')
                if len(parts) != 2 or parts[-1] not in ['view', 'use']:
                    return HttpResponse(':x: Permission {} is not correct'.format(name))
            else:
                name = '{}.use'.format(name)

            description = ' '.join(args[2:])

            if AppPermission.objects.filter(name=name).exists():
                return HttpResponse(':x: Permission {} already exists'.format(name))

            AppPermission.objects.create(name=name, description=description)

            return HttpResponse('Permission {} successfully created'.format(name))

        elif command == 'list':
            table = texttable.Texttable(max_width=0)
            table.set_deco(texttable.Texttable.HEADER)
            table.header(['Name', 'Description', 'Plans', 'Bundles'])

            for p in AppPermission.objects.all():
                table.add_row([p.name, p.description, p.groupplan_set.count(), p.featurebundle_set.count()])

            return JsonResponse({
                'text': 'Permissions List:\n```\n{}\n```'.format(table.draw())
            })

        elif command == 'view':
            name = args[1]
            if not AppPermission.objects.filter(name=name).exists():
                return HttpResponse(':x: Permission {} does not exists'.format(name))

            permission = AppPermission.objects.get(name=name)

            plans_table = texttable.Texttable(max_width=0)
            plans_table.set_deco(texttable.Texttable.HEADER)
            plans_table.header(['ID', 'Title', 'Gateway'])
            for p in permission.groupplan_set.all():
                plans_table.add_row([p.id, p.title, p.payment_gateway])

            plans_perms = texttable.Texttable(max_width=0)
            plans_perms.set_deco(texttable.Texttable.HEADER)
            plans_perms.header(['ID', 'Title'])
            for p in permission.featurebundle_set.all():
                plans_perms.add_row([p.id, p.title])

            return JsonResponse({
                'text': 'Permission {} added to Plans:\n```{}```\nBundles:\n```{}```'.format(
                    name,
                    plans_table.draw() if permission.groupplan_set.count() else 'None',
                    plans_perms.draw() if permission.featurebundle_set.count() else 'None')
            })

        elif command == 'add':
            add_to = args[1]
            add_query = args[2]
            perm_name = args[3]

            if not AppPermission.objects.filter(name=perm_name).exists():
                return HttpResponse(':x: Permission {} does not exists'.format(perm_name))

            permission = AppPermission.objects.get(name=perm_name)

            if add_to == 'plan':
                titles = []
                plans = GroupPlan.objects.filter(id__in=add_query.split(','))
                for plan in plans:
                    titles.append(plan.title)
                    plan.permissions.add(permission)

                return HttpResponse(f'Permission {permission.name} added to Plan: {", ".join(titles)}')

            elif add_to == 'bundle':
                titles = []
                bundles = FeatureBundle.objects.filter(id__in=add_query.split(','))
                for bundle in bundles:
                    titles.append(bundle.title)
                    bundle.permissions.add(permission)

                return HttpResponse(f'Permission {permission.name} added to Bundle: {", ".join(titles)}')

            else:
                return HttpResponse(f':x: Target is not known {add_to}')

        elif command == 'remove':
            add_to = args[1]
            add_query = args[2]
            perm_name = args[3]

            if not AppPermission.objects.filter(name=perm_name).exists():
                return HttpResponse(':x: Permission {} does not exists'.format(perm_name))

            permission = AppPermission.objects.get(name=perm_name)

            if add_to == 'plan':
                titles = []
                plans = GroupPlan.objects.filter(id__in=add_query.split(','))
                for plan in plans:
                    titles.append(plan.title)
                    plan.permissions.remove(permission)

                return HttpResponse(f'Permission {permission.name} removed from Plan: {", ".join(titles)}')

            elif add_to == 'bundle':
                titles = []
                bundles = FeatureBundle.objects.filter(id__in=add_query.split(','))
                for bundle in bundles:
                    titles.append(bundle.title)
                    bundle.permissions.remove(permission)

                return HttpResponse(f'Permission {permission.name} removed from Bundle: {", ".join(titles)}')

            else:
                return HttpResponse(f':x: Target is not known {add_to}')

        elif command == 'copy':
            if len(args) != 3:
                return HttpResponse(f":x: Usage: {request.POST['command']} {command} <source plan id> <destination plan id>")

            if not request_from.is_superuser:
                return HttpResponse(":x: Copy plan for admin only")

            try:
                source_plan = GroupPlan.objects.get(id=args[1])
                destination_plan = GroupPlan.objects.get(id=args[2])
            except GroupPlan.DoesNotExist:
                return HttpResponse(":x: Plan does not exists (use plan IDs)")

            for p in source_plan.permissions.all():
                destination_plan.permissions.add(p)

            return HttpResponse(f'Permission copied from *{source_plan.title}* to *{destination_plan.title}*')

    elif request.POST['command'] == '/affiliate':
        args = request.POST['text'].split(' ')
        command = args[0]

        if command in ['disable', 'enable', 'disable_always', 'enable_always']:
            if len(args) != 2:
                return HttpResponse(':x: Wrong number of arguments')

            user_id = args[1]

            if safe_int(user_id):
                user = User.objects.get(id=user_id)
            else:
                try:
                    user = User.objects.get(email__iexact=user_id)
                except User.MultipleObjectsReturned:
                    return HttpResponse(':x: Multiple users with same email found, use user ID instead of email')

            if command in ['enable', 'disable']:
                if command == 'enable':
                    user.set_config('_disable_affiliate', False)
                elif command == 'disable':
                    user.set_config('_disable_affiliate', True)

                if user.models_user != user:
                    return HttpResponse(f':ok: Affiliate {command}d for *sub user* {user.email} '
                                        f':warning: Parent account {user.models_user.email} must be set separately')
                else:
                    return HttpResponse(f':ok: Affiliate {command}d for {user.email}')

            elif command in ['enable_always', 'disable_always']:
                if command == 'enable_always':
                    user.set_config('_disable_affiliate_permanent', False)
                elif command == 'disable_always':
                    user.set_config('_disable_affiliate_permanent', True)

                if user.models_user != user:
                    return HttpResponse(f':ok: Affiliate {command} for sub user {user.email} '
                                        f':warning: Parent account {user.models_user.email} must be set separately')
                else:
                    return HttpResponse(f':ok: Affiliate {command} for {user.email}')

        else:
            return HttpResponse(':x: Unknown Command: {} {}'.format(request.POST['command'], command))
    #
    elif request.POST['command'] == '/plan-coupon':
        args = request.POST['text'].split(' ')
        if len(args) != 2:
            return HttpResponse(':x: usage: /plan-coupon <plan id> <coupon id>')

        plan = args[0]
        coupon = args[1]

        try:
            reg_coupon = stripe.Coupon.retrieve(coupon)

            if not reg_coupon.valid:
                return HttpResponse(f':x: Coupon {coupon} is not valid')

        except:
            return HttpResponse(f':x: Coupon {coupon} not found')

        try:
            plan = GroupPlan.objects.get(id=plan)

            if not plan.is_stripe():
                return HttpResponse(f':x: Plan *{plan.title}* is not Stripe plan')

            if plan.locked:
                plan.locked = False
                plan.save()

        except GroupPlan.DoesNotExist:
            return HttpResponse(f':x: Plan {plan} not found')

        coupon_sign = base64_encode(Signer().sign(reg_coupon.id))

        url = app_link(f'accounts/register/{plan.slug}-subscribe', cp=coupon_sign)

        return HttpResponse(f'OK => {url}')

    elif request.POST['command'] == '/login-as':
        return HttpResponse(':x: You can now login directly from Admin Users Search page\n'
                            'Search by a customer email then click "Options" then "Login as this user"')

    elif request.POST['command'] == '/user-flags':
        args = [i.strip() for i in request.POST['text'].split(' ') if i.strip()]
        if not args:
            return HttpResponse('Available Flags:\n' + '\n'.join(['- woocommerce-alerts: Enable fix for WooCommerce Alerts page not loading']))

        flag, email = args

        try:
            user_id = safe_int(email, None)
            if user_id is not None:
                user = User.objects.get(id=user_id)
            else:
                user = User.objects.get(email__iexact=email)
        except:
            return HttpResponse(f':x: User not found {email} (or duplicate accounts)')

        if flag == 'woocommerce-alerts':
            user.set_config('_woo_alerts_variants_fix', True)
            return HttpResponse(f':ok: Flag *{flag}* enabled for {user.email}')
        else:
            return HttpResponse(f':x: Flag not found *{flag}*')

    elif request.POST['command'] == '/record-transaction':
        args = [i.strip() for i in request.POST['text'].split(' ') if i.strip()]
        if not args or len(args) != 3:
            return HttpResponse(':x: Usage: /record-transaction <email> <amount> <transaction id>')

        email, amount, transaction_id = args

        amount = safe_float(amount)
        if not amount:
            return HttpResponse(f':x: Amount is not set or malformatted ({amount})')

        try:
            user_id = safe_int(email, None)
            if user_id is not None:
                user = User.objects.get(id=user_id)
            else:
                user = User.objects.get(email__iexact=email)
        except:
            return HttpResponse(f':x: User not found {email} (or duplicate accounts) {request_from.email}')

        pls_orders_count = 0
        pls_orders_amount = 0.0
        pls_orders_id = []

        pls_orders = PLSOrder.objects.filter(user=user).filter(Q(stripe_transaction_id='') | Q(stripe_transaction_id=None)) \
                                     .order_by('id')

        for i in pls_orders:
            pls_orders_amount = pls_orders_amount + (i.amount * 0.01)
            pls_orders_count += 1
            pls_orders_id.append(i.id)

            if pls_orders_amount >= amount:
                break

        PLSOrder.objects.filter(id__in=pls_orders_id).update(stripe_transaction_id=transaction_id)

        AdminEvent.objects.create(
            user=request_from,
            event_type='record_transaction',
            target_user=user,
            data=json.dumps({
                'transaction_id': transaction_id,
                'amount': amount,
                'pls_orders_amount': pls_orders_amount,
                'pls_orders_count': pls_orders_count
            }))

        return HttpResponse(f':ok: User {user.email} transactions updated for {pls_orders_count} Orders, Total ${pls_orders_amount}')

    elif request.POST['command'] == '/shipstation':
        # Available Commands:
        # /shipstation <order_number>

        args = request.POST['text'].split(' ')
        order_number = args[0]
        from product_common.lib.shipstation import get_shipstation_shipments
        url = f'{settings.SHIPSTATION_API_URL}/shipments?includeShipmentItems=True&orderNumber={order_number}'
        shipments = get_shipstation_shipments(url)

        result = []
        for shipment in shipments:
            shipment_items = shipment['shipmentItems'] or []
            items = [i['sku'] for k, i in enumerate(shipment_items) if k % 2 == 0]
            result.append(f"{shipment['trackingNumber']}: {', '.join(items)}")

        return HttpResponse('Results:\n{}'.format('\n'.join(result if result else ['Not found'])))

    else:
        return HttpResponse(':x: Unknown Command: {}'.format(request.POST['command']))


def activecampaign_trial(request):
    user_id = request.POST.get('contact[fields][dropified_id]')
    email = request.POST.get('contact[email]')
    user = get_object_or_404(User, id=user_id, email=email)

    api = ActiveCampaignAPI()
    api.update_customer({
        'email': user.email,
        'custom_fields': api.get_user_plan_data(user)
    }, version='1')

    return HttpResponse({'status': 'ok'})


def intercom_activecampaign(request):
    key = bytes(settings.AC_INTERCOM_SECRET, 'utf8')
    digester = hmac.new(key=key, msg=request.body, digestmod=sha1)
    signature = f"sha1={digester.hexdigest()}"
    if request.META['HTTP_X_HUB_SIGNATURE'] != signature:
        return HttpResponse(status=403)

    payload = json.loads(request.body)
    intercom_contact = payload['data']['item']
    api = ActiveCampaignAPI()

    if payload['topic'] == 'user.unsubscribed':
        contact_data = {
            'email': intercom_contact['email'],
            'custom_fields': {
                'SEND_EMAILS': not intercom_contact['unsubscribed_from_emails']
            }
        }
        api.update_customer(contact_data, version='1')
        return HttpResponse()

    elif payload['topic'] in ['contact.created', 'contact.added_email']:
        user = User.objects.filter(email=intercom_contact['email']).first()
        if user is None:
            contact_data = api.get_intercom_data(intercom_contact)
        else:
            contact_data = api.get_user_data(user)

        api.update_customer(contact_data, version='1')
        return HttpResponse()


def alibaba_webhook(request):
    alibaba_user_id = request.GET['user_id']
    product_id = request.GET['id']
    products_data = {
        alibaba_user_id: [product_id],
    }

    alibaba_utils.save_alibaba_products(request, products_data)

    return HttpResponse('ok')
