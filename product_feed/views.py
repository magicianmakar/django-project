from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
from django.utils import timezone
from django.http import JsonResponse

from raven.contrib.django.raven_compat.models import client as raven_client

from leadgalaxy.models import ShopifyStore

from .feed import get_store_feed, generate_product_feed
from .models import FeedStatus


@login_required
def product_feeds(request):
    if not request.user.can('product_feeds.use'):
        return render(request, 'upgrade.html')

    if request.method == 'POST':
        if request.POST.get('feed'):

            try:
                feed = FeedStatus.objects.get(id=request.POST['feed'], store__user=request.user)

            except FeedStatus.DoesNotExist:
                return JsonResponse({'error': 'Feed Not Found'}, status=500)

            if request.POST.get('all_variants'):
                # Change all variants setting
                feed.all_variants = request.POST['all_variants'] == 'true'
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
    for store in request.user.profile.get_active_stores():
        feeds.append(get_store_feed(store))

    return render(request, 'product_feeds.html', {
        'feeds': feeds,
        'now': timezone.now(),
        'page': 'product_feeds',
        'breadcrumbs': ['Marketing', 'Product Feeds']
    })


def get_product_feed(request, store_id, revision=None):
    try:
        assert len(store_id) == 8
        store = ShopifyStore.objects.get(store_hash__startswith=store_id)

        assert store.get_info
    except (Exception, AssertionError, ShopifyStore.DoesNotExist):
        raise Http404('Feed not found')

    if not store.user.can('product_feeds.use'):
        raise PermissionDenied('Product Feeds')

    nocache = request.GET.get('nocache') == '1'

    if revision is None:
        revision = 1

    feed = get_store_feed(store)  # Get feed or create it if doesn't exists
    feed.revision = revision

    if 'facebookexternalhit' in request.META.get('HTTP_USER_AGENT', '') or request.GET.get('f') == '1':
        from leadgalaxy.tasks import generate_feed

        fb_update_key = 'product_feed_update_{}'.format(feed.id)

        # Schedule an update only if it wasn't done before
        if cache.get(fb_update_key) is None:
            next_eta = timezone.now() + timezone.timedelta(seconds=2700)
            generate_feed.apply_async(args=[feed.id], kwargs={'nocache': True, 'by_fb': True}, eta=next_eta)

            cache.set(fb_update_key, True, timeout=36000)

        feed.fb_access_at = timezone.now()

    feed.save()

    feed_s3_url = generate_product_feed(feed, nocache=nocache)

    if feed_s3_url:
        return HttpResponseRedirect(feed_s3_url)
    else:
        raven_client.captureMessage('Product Feed not found', level='warning')
        raise Http404('Product Feed not found')
