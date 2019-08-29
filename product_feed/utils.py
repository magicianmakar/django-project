from django.utils import timezone


def is_bot_useragent(request):
    ua = request.META.get('HTTP_USER_AGENT', '')
    return any(['facebookexternalhit' in ua, 'googlebot' in ua])


def update_feed_social_access_at(feed, request):
    if 'facebookexternalhit' in request.META.get('HTTP_USER_AGENT', '') or request.GET.get('f') == '1':
        feed.fb_access_at = timezone.now()

    if 'googlebot' in request.META.get('HTTP_USER_AGENT', '').lower():
        feed.google_access_at = timezone.now()
