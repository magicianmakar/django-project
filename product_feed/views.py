import json

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.utils import timezone
from django.http import JsonResponse
from raven.contrib.django.raven_compat.models import client as raven_client

from shopified_core import permissions
from leadgalaxy.models import ShopifyStore
from commercehq_core.models import CommerceHQStore
from woocommerce_core.models import WooStore
from gearbubble_core.models import GearBubbleStore
from groovekart_core.models import GrooveKartStore
from bigcommerce_core.models import BigCommerceStore

from .feed import (
    get_store_feed,
    generate_product_feed,
    get_chq_store_feed,
    generate_chq_product_feed,
    get_woo_store_feed,
    generate_woo_product_feed,
    get_gear_store_feed,
    generate_gear_product_feed,
    get_gkart_store_feed,
    generate_gkart_product_feed,
    get_bigcommerce_store_feed,
    generate_bigcommerce_product_feed,
)
from .models import (
    FeedStatus,
    CommerceHQFeedStatus,
    WooFeedStatus,
    GearBubbleFeedStatus,
    GrooveKartFeedStatus,
    BigCommerceFeedStatus,
)
from .utils import is_bot_useragent, update_feed_social_access_at


@login_required
def product_feeds(request, *args, **kwargs):
    if not kwargs.get('store_type'):
        return shopify_product_feeds(request)
    if kwargs.get('store_type') == 'chq':
        return chq_product_feeds(request)
    if kwargs.get('store_type') == 'woo':
        return woo_product_feeds(request)
    if kwargs.get('store_type') == 'gear':
        return gear_product_feeds(request)
    if kwargs.get('store_type') == 'gkart':
        return gkart_product_feeds(request)
    if kwargs.get('store_type') == 'bigcommerce':
        return bigcommerce_product_feeds(request)

    raise Http404('Feed Type is not found')


def get_product_feed(request, *args, **kwargs):
    store_type = kwargs.get('store_type')

    if 'store_type' in kwargs:
        del kwargs['store_type']

    feed = None
    if not store_type:
        feed = get_shopify_product_feed(request, *args, **kwargs)
    if store_type == 'chq':
        feed = get_chq_product_feed(request, *args, **kwargs)
    if store_type == 'woo':
        feed = get_woo_product_feed(request, *args, **kwargs)
    if store_type == 'gear':
        feed = get_gear_product_feed(request, *args, **kwargs)
    if store_type == 'gkart':
        feed = get_gkart_product_feed(request, *args, **kwargs)
    if store_type == 'bigcommerce':
        feed = get_bigcommerce_product_feed(request, *args, **kwargs)

    if not feed:
        raise Http404('Feed Type is not found')

    if not is_bot_useragent(request):
        return HttpResponse('Your feed works, please copy/paste this link to your Facebook or Google product feed to see it\'s content')

    return feed


def shopify_product_feeds(request):
    if not request.user.can('product_feeds.use'):
        return render(request, 'upgrade.html', {'selected_menu': 'tools:product_feeds'})

    if request.GET.get('type') == 'google-feed-settings' or request.POST.get('type') == 'google-feed-settings':
        if request.method == 'GET':
            try:
                feed = FeedStatus.objects.get(id=request.GET['feed'])
                permissions.user_can_view(request.user, feed.store)

            except FeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            return JsonResponse(feed.get_google_settings())

        elif request.method == 'POST':
            try:
                feed = FeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except FeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            settings = json.loads(request.POST['settings'])
            feed.set_google_settings(settings)

            return JsonResponse(feed.get_google_settings())

    if request.method == 'POST':
        if request.POST.get('feed'):

            try:
                feed = FeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except FeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            if request.POST.get('all_variants'):
                # Change all variants setting
                feed.all_variants = request.POST['all_variants'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('include_variants_id'):
                feed.include_variants_id = request.POST['include_variants_id'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('default_product_category'):
                feed.default_product_category = request.POST['default_product_category'].strip()
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('update_feed'):
                if feed.status == 2:
                    return JsonResponse({'error': 'Feed is being updated'}, status=500)

                from leadgalaxy.tasks import generate_feed

                generate_feed.delay(feed.id, nocache=True)
                return JsonResponse({'status': 'ok'})

        return JsonResponse({'error': 'Missing parameters'}, status=500)

    feeds = []
    for store in request.user.profile.get_shopify_stores():
        feeds.append(get_store_feed(store))

    return render(request, 'product_feeds.html', {
        'feeds': feeds,
        'now': timezone.now(),
        'page': 'product_feeds',
        'selected_menu': 'tools:product_feeds',
        'breadcrumbs': ['Marketing', 'Product Feeds']
    })


def get_shopify_product_feed(request, store_id, revision=None):
    try:
        assert len(store_id) == 8
        store = ShopifyStore.objects.get(store_hash__startswith=store_id)

        assert store.get_info
    except (Exception, AssertionError, ShopifyStore.DoesNotExist):
        raise Http404('Feed not found')

    if not store.user.can('product_feeds.use'):
        raise Http404('Product Feeds')

    nocache = request.GET.get('nocache') == '1'

    try:
        revision = int(revision)
    except:
        revision = 1

    feed = get_store_feed(store)  # Get feed or create it if doesn't exists
    update_feed_social_access_at(feed, request)
    feed.save()

    feed_s3_url = generate_product_feed(feed, nocache=nocache, revision=revision)

    if feed_s3_url:
        return HttpResponseRedirect(f'{feed_s3_url}?v={feed.updated_version}')
    else:
        raven_client.captureMessage('Product Feed not found', level='warning')
        raise Http404('Product Feed not found')


def chq_product_feeds(request):
    if not request.user.can('product_feeds.use'):
        return render(request, 'commercehq/upgrade.html')

    if request.GET.get('type') == 'google-feed-settings' or request.POST.get('type') == 'google-feed-settings':
        if request.method == 'GET':
            try:
                feed = CommerceHQFeedStatus.objects.get(id=request.GET['feed'])
                permissions.user_can_view(request.user, feed.store)

            except CommerceHQFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            return JsonResponse(feed.get_google_settings())

        elif request.method == 'POST':
            try:
                feed = CommerceHQFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except CommerceHQFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            settings = json.loads(request.POST['settings'])
            feed.set_google_settings(settings)

            return JsonResponse(feed.get_google_settings())

    if request.method == 'POST':
        if request.POST.get('feed'):

            try:
                feed = CommerceHQFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except CommerceHQFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            if request.POST.get('all_variants'):
                # Change all variants setting
                feed.all_variants = request.POST['all_variants'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('include_variants_id'):
                feed.include_variants_id = request.POST['include_variants_id'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('default_product_category'):
                feed.default_product_category = request.POST['default_product_category'].strip()
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('update_feed'):
                if feed.status == 2:
                    return JsonResponse({'error': 'Feed is being updated'}, status=500)

                from leadgalaxy.tasks import generate_chq_feed

                generate_chq_feed.delay(feed.id, nocache=True)
                return JsonResponse({'status': 'ok'})

        return JsonResponse({'error': 'Missing parameters'}, status=500)

    feeds = []
    for store in request.user.profile.get_chq_stores():
        feeds.append(get_chq_store_feed(store))

    return render(request, 'chq_product_feeds.html', {
        'feeds': feeds,
        'now': timezone.now(),
        'page': 'product_feeds',
        'selected_menu': 'tools:product_feeds',
        'breadcrumbs': ['Marketing', 'Product Feeds']
    })


def get_chq_product_feed(request, store_id, revision=None):
    try:
        assert len(store_id) == 8
        store = CommerceHQStore.objects.get(store_hash__startswith=store_id)
    except (Exception, AssertionError, CommerceHQStore.DoesNotExist):
        raise Http404('Feed not found')

    if not store.user.can('product_feeds.use'):
        raise Http404('Product Feeds')

    nocache = request.GET.get('nocache') == '1'

    if revision is None:
        revision = 1

    feed = get_chq_store_feed(store)  # Get feed or create it if doesn't exists
    feed.revision = revision
    update_feed_social_access_at(feed, request)
    feed.save()

    feed_s3_url = generate_chq_product_feed(feed, nocache=nocache)

    if feed_s3_url:
        return HttpResponseRedirect(f'{feed_s3_url}?v={feed.updated_version}')
    else:
        raven_client.captureMessage('Product Feed not found', level='warning')
        raise Http404('Product Feed not found')


def woo_product_feeds(request):
    if not request.user.can('product_feeds.use'):
        return render(request, 'woocommerce/upgrade.html')

    if request.GET.get('type') == 'google-feed-settings' or request.POST.get('type') == 'google-feed-settings':
        if request.method == 'GET':
            try:
                feed = WooFeedStatus.objects.get(id=request.GET['feed'])
                permissions.user_can_view(request.user, feed.store)

            except WooFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            return JsonResponse(feed.get_google_settings())

        elif request.method == 'POST':
            try:
                feed = WooFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except WooFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            settings = json.loads(request.POST['settings'])
            feed.set_google_settings(settings)

            return JsonResponse(feed.get_google_settings())

    if request.method == 'POST':
        if request.POST.get('feed'):

            try:
                feed = WooFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except WooFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            if request.POST.get('all_variants'):
                # Change all variants setting
                feed.all_variants = request.POST['all_variants'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('include_variants_id'):
                feed.include_variants_id = request.POST['include_variants_id'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('default_product_category'):
                feed.default_product_category = request.POST['default_product_category'].strip()
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('update_feed'):
                if feed.status == 2:
                    return JsonResponse({'error': 'Feed is being updated'}, status=500)

                from leadgalaxy.tasks import generate_woo_feed

                generate_woo_feed.delay(feed.id, nocache=True)
                return JsonResponse({'status': 'ok'})

        return JsonResponse({'error': 'Missing parameters'}, status=500)

    feeds = []
    for store in request.user.profile.get_woo_stores():
        feeds.append(get_woo_store_feed(store))

    return render(request, 'woo_product_feeds.html', {
        'feeds': feeds,
        'now': timezone.now(),
        'page': 'product_feeds',
        'selected_menu': 'tools:product_feeds',
        'breadcrumbs': ['Marketing', 'Product Feeds']
    })


def get_woo_product_feed(request, store_id, revision=None):
    try:
        assert len(store_id) == 8
        store = WooStore.objects.get(store_hash__startswith=store_id)
    except (Exception, AssertionError, WooStore.DoesNotExist):
        raise Http404('Feed not found')

    if not store.user.can('product_feeds.use'):
        raise Http404('Product Feeds')

    nocache = request.GET.get('nocache') == '1'

    if revision is None:
        revision = 1

    feed = get_woo_store_feed(store)  # Get feed or create it if doesn't exists
    feed.revision = revision
    update_feed_social_access_at(feed, request)
    feed.save()

    feed_s3_url = generate_woo_product_feed(feed, nocache=nocache)

    if feed_s3_url:
        return HttpResponseRedirect(f'{feed_s3_url}?v={feed.updated_version}')
    else:
        raven_client.captureMessage('Product Feed not found', level='warning')
        raise Http404('Product Feed not found')


def gear_product_feeds(request):
    if not request.user.can('product_feeds.use'):
        return render(request, 'gearbubble/upgrade.html')

    if request.method == 'POST':
        if request.POST.get('feed'):

            try:
                feed = GearBubbleFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except GearBubbleFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            if request.POST.get('all_variants'):
                # Change all variants setting
                feed.all_variants = request.POST['all_variants'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('include_variants_id'):
                feed.include_variants_id = request.POST['include_variants_id'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('default_product_category'):
                feed.default_product_category = request.POST['default_product_category'].strip()
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('update_feed'):
                if feed.status == 2:
                    return JsonResponse({'error': 'Feed is being updated'}, status=500)

                from leadgalaxy.tasks import generate_gear_feed

                generate_gear_feed.delay(feed.id, nocache=True)
                return JsonResponse({'status': 'ok'})

        return JsonResponse({'error': 'Missing parameters'}, status=500)

    feeds = []
    for store in request.user.profile.get_gear_stores():
        feeds.append(get_gear_store_feed(store))

    return render(request, 'gear_product_feeds.html', {
        'feeds': feeds,
        'now': timezone.now(),
        'page': 'product_feeds',
        'selected_menu': 'tools:product_feeds',
        'breadcrumbs': ['Marketing', 'Product Feeds']
    })


def get_gear_product_feed(request, store_id, revision=None):
    try:
        assert len(store_id) == 8
        store = GearBubbleStore.objects.get(store_hash__startswith=store_id)
    except (Exception, AssertionError, GearBubbleStore.DoesNotExist):
        raise Http404('Feed not found')

    if not store.user.can('product_feeds.use'):
        raise Http404('Product Feeds')

    nocache = request.GET.get('nocache') == '1'

    if revision is None:
        revision = 1

    feed = get_gear_store_feed(store)  # Get feed or create it if doesn't exists
    feed.revision = revision
    update_feed_social_access_at(feed, request)
    feed.save()

    feed_s3_url = generate_gear_product_feed(feed, nocache=nocache)

    if feed_s3_url:
        return HttpResponseRedirect(f'{feed_s3_url}?v={feed.updated_version}')
    else:
        raven_client.captureMessage('Product Feed not found', level='warning')
        raise Http404('Product Feed not found')


def gkart_product_feeds(request):
    if not request.user.can('product_feeds.use'):
        return render(request, 'groovekart/upgrade.html')

        if request.GET.get('type') == 'google-feed-settings' or request.POST.get('type') == 'google-feed-settings':
            if request.method == 'GET':
                try:
                    feed = GrooveKartFeedStatus.objects.get(id=request.GET['feed'])
                    permissions.user_can_view(request.user, feed.store)

                except GrooveKartFeedStatus.DoesNotExist:
                    return JsonResponse({'error': 'Feed Not Found'}, status=500)

                return JsonResponse(feed.get_google_settings())

        elif request.method == 'POST':
            try:
                feed = GrooveKartFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except GrooveKartFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            settings = json.loads(request.POST['settings'])
            feed.set_google_settings(settings)

            return JsonResponse(feed.get_google_settings())

    if request.method == 'POST':
        if request.POST.get('feed'):

            try:
                feed = GrooveKartFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except GrooveKartFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            if request.POST.get('all_variants'):
                # Change all variants setting
                feed.all_variants = request.POST['all_variants'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('include_variants_id'):
                feed.include_variants_id = request.POST['include_variants_id'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('default_product_category'):
                feed.default_product_category = request.POST['default_product_category'].strip()
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('update_feed'):
                if feed.status == 2:
                    return JsonResponse({'error': 'Feed is being updated'}, status=500)

                from leadgalaxy.tasks import generate_gkart_feed

                generate_gkart_feed.delay(feed.id, nocache=True)
                return JsonResponse({'status': 'ok'})

        return JsonResponse({'error': 'Missing parameters'}, status=500)

    feeds = []
    for store in request.user.profile.get_gkart_stores():
        feeds.append(get_gkart_store_feed(store))

    return render(request, 'gkart_product_feeds.html', {
        'feeds': feeds,
        'now': timezone.now(),
        'page': 'product_feeds',
        'selected_menu': 'tools:product_feeds',
        'breadcrumbs': ['Marketing', 'Product Feeds']
    })


def get_gkart_product_feed(request, store_id, revision=None):
    try:
        assert len(store_id) == 8
        store = GrooveKartStore.objects.get(store_hash__startswith=store_id)
    except (Exception, AssertionError, GrooveKartStore.DoesNotExist):
        raise Http404('Feed not found')

    if not store.user.can('product_feeds.use'):
        raise Http404('Product Feeds')

    nocache = request.GET.get('nocache') == '1'

    if revision is None:
        revision = 1

    feed = get_gkart_store_feed(store)  # Get feed or create it if doesn't exists
    feed.revision = revision
    update_feed_social_access_at(feed, request)
    feed.save()

    feed_s3_url = generate_gkart_product_feed(feed, nocache=nocache)

    if feed_s3_url:
        return HttpResponseRedirect(f'{feed_s3_url}?v={feed.updated_version}')
    else:
        raven_client.captureMessage('Product Feed not found', level='warning')
        raise Http404('Product Feed not found')


def bigcommerce_product_feeds(request):
    if not request.user.can('product_feeds.use'):
        return render(request, 'bigcommerce/upgrade.html')

    if request.GET.get('type') == 'google-feed-settings' or request.POST.get('type') == 'google-feed-settings':
        if request.method == 'GET':
            try:
                feed = BigCommerceFeedStatus.objects.get(id=request.GET['feed'])
                permissions.user_can_view(request.user, feed.store)

            except BigCommerceFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            return JsonResponse(feed.get_google_settings())

        elif request.method == 'POST':
            try:
                feed = BigCommerceFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except BigCommerceFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            settings = json.loads(request.POST['settings'])
            feed.set_google_settings(settings)

            return JsonResponse(feed.get_google_settings())

    if request.method == 'POST':
        if request.POST.get('feed'):

            try:
                feed = BigCommerceFeedStatus.objects.get(id=request.POST['feed'])
                permissions.user_can_view(request.user, feed.store)

            except BigCommerceFeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            if request.POST.get('all_variants'):
                # Change all variants setting
                feed.all_variants = request.POST['all_variants'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('include_variants_id'):
                feed.include_variants_id = request.POST['include_variants_id'] == 'true'
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('default_product_category'):
                feed.default_product_category = request.POST['default_product_category'].strip()
                feed.save()

                return JsonResponse({'status': 'ok'})

            elif request.POST.get('update_feed'):
                if feed.status == 2:
                    return JsonResponse({'error': 'Feed is being updated'}, status=500)

                from leadgalaxy.tasks import generate_bigcommerce_feed

                generate_bigcommerce_feed.delay(feed.id, nocache=True)
                return JsonResponse({'status': 'ok'})

        return JsonResponse({'error': 'Missing parameters'}, status=500)

    feeds = []
    for store in request.user.profile.get_bigcommerce_stores():
        feeds.append(get_bigcommerce_store_feed(store))

    return render(request, 'bigcommerce_product_feeds.html', {
        'feeds': feeds,
        'now': timezone.now(),
        'page': 'product_feeds',
        'selected_menu': 'tools:product_feeds',
        'breadcrumbs': ['Marketing', 'Product Feeds']
    })


def get_bigcommerce_product_feed(request, store_id, revision=None):
    try:
        assert len(store_id) == 8
        store = BigCommerceStore.objects.get(store_hash__startswith=store_id)
    except (Exception, AssertionError, BigCommerceStore.DoesNotExist):
        raise Http404('Feed not found')

    if not store.user.can('product_feeds.use'):
        raise Http404('Product Feeds')

    nocache = request.GET.get('nocache') == '1'

    if revision is None:
        revision = 1

    feed = get_bigcommerce_store_feed(store)  # Get feed or create it if doesn't exists
    feed.revision = revision
    update_feed_social_access_at(feed, request)
    feed.save()

    feed_s3_url = generate_bigcommerce_product_feed(feed, nocache=nocache)

    if feed_s3_url:
        return HttpResponseRedirect(f'{feed_s3_url}?v={feed.updated_version}')
    else:
        raven_client.captureMessage('Product Feed not found', level='warning')
        raise Http404('Product Feed not found')
