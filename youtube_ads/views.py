import urllib2
import re
import json
import requests

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.shortcuts import render, redirect, reverse, get_object_or_404
from django.core.paginator import Paginator
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from raven.contrib.django.raven_compat.models import client as raven_client

from .utils import Youtube, get_videos_info, get_channels_info
from .models import VideosList
from .decorators import feature_permission_required


def JsonResponse(data):
    return HttpResponse(json.dumps(data, sort_keys=True, indent=4),
                        content_type='application/json; charset=UTF-8')


@login_required
@feature_permission_required
def autocomplete(request):
    q = request.GET.get('q')

    headers = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'en,fr;q=0.8,fr-FR;q=0.5,en-US;q=0.3',
        'Connection': 'keep-alive',
        'DNT': '1',
        'Host': 'clients1.google.com',
        'Referer': 'https://www.youtube.com/',
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux i686; rv:38.0) Gecko/20100101 Firefox/38.0',
    }
    url = (
        'https://clients1.google.com/complete/search?'
        'client=youtube&hl=en&gl=ma&gs_rn=23&gs_ri=youtube&ds=yt&cp=4&gs_id=h&'
        'q=%s&callback=google.sbox.p50&gs_gbg=O1x8jxdhuqvwV62b34' % q
    )
    r = requests.get(url, headers=headers)
    res = re.findall('\["([^"]+)"', r.text)

    return JsonResponse(res)


@login_required
@feature_permission_required
def index(request):
    error = None
    current_page = ('youtube_related' if 'r' in request.GET else 'youtube_search')
    breadcrumbs = [
        {'url': reverse('youtube_ads.views.index'), 'title': 'TubeHunt'},
        'Search'
    ]

    if request.GET.get('q') or request.GET.get('r'):
        query = urllib2.unquote(request.GET.get('q', request.GET.get('r')))

        try:
            youtube = Youtube(request)
            if not youtube.client:
                return redirect('youtube_ads.views.auth')

            is_related = 'r' in request.GET

            if is_related:
                try:
                    validate = URLValidator()
                    validate(query)
                except ValidationError:
                    query = "https://www.youtube.com/watch?v={}".format(query)

            search_response, query = youtube.search(query, page=request.GET.get('page'), related=is_related)

            videos = []
            for item in search_response['items']:
                if item['id']['kind'] == 'youtube#video':
                    videos.append(item['id']['videoId'])

            videos = get_videos_info(
                youtube.client,
                videos,
                request.GET.get('type') == 'all',
                count=int(request.GET.get('offset', 0))
            )

            if is_related:
                breadcrumbs[1] = 'Related'

            return render(request, 'youtube_ads/index.html', {
                'videos': videos,
                'query': query,
                'related': is_related,
                'page': current_page,
                'offset_next': videos[-1]['index'],
                'offset_prev': request.GET.get('op', videos[0]['index'] - 1),
                'search_next': search_response.get('nextPageToken'),
                'search_prev': search_response.get('prevPageToken'),
                'breadcrumbs': breadcrumbs,
            })

        except Exception as e:
            if 'Invalid video' in str(e):
                error = 'Invalid video: {}'.format(request.GET.get('r'))
                return redirect('{}?q={}'.format(reverse('youtube_ads.views.index'), request.GET.get('r')))
            if 'Invalid channel' in str(e):
                error = 'Invalid Channel: {}'.format(request.GET.get('r'))
            else:
                error = "Sorry! Something went wrong, we're working on it. Please try again in a few minutes."
                raven_client.captureException()

    return render(request, 'youtube_ads/index.html', {
        'related': 'r' in request.GET,
        'page': current_page,
        'error': error,
        'breadcrumbs': breadcrumbs,
    })


@login_required
@feature_permission_required
def channels(request):
    error = None
    breadcrumbs = [
        {'url': reverse('youtube_ads.views.index'), 'title': 'TubeHunt'},
        'Channels'
    ]

    if request.GET.get('q'):
        query = urllib2.unquote(request.GET.get('q'))
        channel = re.findall('channel[:/]([^/?]+)', query)
        if len(channel):
            return redirect('{}?q=channel:{}'.format(reverse('youtube_ads.views.index'), channel[0]))

        try:
            youtube = Youtube(request)
            if not youtube.client:
                return redirect('youtube_ads.views.auth')

            search_response = youtube.channels(query)

            channels = []
            for item in search_response['items']:
                channels.append(item['id']['channelId'])

            channels = get_channels_info(youtube.client, channels)

            return render(request, 'youtube_ads/channels.html', {
                'channels': channels,
                'query': request.GET.get('q'),
                'page': 'youtube_channels'
            })

        except Exception as e:
            if 'Invalid video' in str(e):
                error = 'Invalid video: %s' % request.GET.get('q')
            if 'Invalid channel' in str(e):
                error = 'Invalid Channel: %s' % request.GET.get('q')
            else:
                error = "Sorry! Something went wrong, we're working on it. Please try again in a few minutes."
                raven_client.captureException()

    return render(request, 'youtube_ads/channels.html', {
        'channels': {},
        'query': '',
        'page': 'youtube_channels',
        'error': error,
        'breadcrumbs': breadcrumbs,
    })


def auth(request):
    youtube = Youtube(request)
    return render(request, 'youtube_ads/auth.html', {
        'oauth_link': youtube.flow.step1_get_authorize_url(),
        'page': 'youtube_search'
    })


def oauth2callback(request):
    youtube = Youtube(request)
    youtube.credentials = youtube.flow.step2_exchange(request.GET.get('code'))

    return redirect('youtube_ads.views.index')


@login_required
@feature_permission_required
def lists(request):
    lists = VideosList.objects.filter(user=request.user)
    breadcrumbs = [
        {'url': reverse('youtube_ads.views.index'), 'title': 'TubeHunt'},
        'Lists'
    ]

    return render(request, 'youtube_ads/lists.html', {
        'lists': lists,
        'breadcrumbs': breadcrumbs,
        'page': 'youtube_lists'
    })


@login_required
@feature_permission_required
def list_detail(request, pk):
    video_list = get_object_or_404(VideosList, pk=pk)
    video_ids = video_list.get_videos()

    paginator = Paginator(video_ids, 50)
    page_number = request.GET.get('page_number', 1)
    page = paginator.page(page_number)

    video_type = request.GET.get('type') == 'all'
    youtube = Youtube(request)
    videos = get_videos_info(youtube.client, page.object_list, video_type)

    breadcrumbs = [
        {'url': reverse('youtube_ads.views.index'), 'title': 'TubeHunt'},
        {'url': reverse('youtube_ads.views.lists'), 'title': 'Lists'},
        video_list.title,
    ]

    context = {'breadcrumbs': breadcrumbs, 'video_list': video_list, 'videos': videos, 'page': page}

    return render(request, 'youtube_ads/list_detail.html', context)
