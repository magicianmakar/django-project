from django.utils import timezone


def is_bot_useragent(request):
    ua = request.META.get('HTTP_USER_AGENT', '').lower()

    if 'facebookexternalhit' in ua:
        return 'fb'
    elif 'googlebot' in ua or 'google-xrawler' in ua:
        return 'google'
    else:
        return None


def update_feed_social_access_at(feed, request):
    ua_name = is_bot_useragent(request)

    if ua_name == 'fb' or request.GET.get('f') == '1':
        feed.fb_access_at = timezone.now()

    if ua_name == 'google' or request.GET.get('f') == 'g':
        feed.google_access_at = timezone.now()
