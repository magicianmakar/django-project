import os
import re
from httplib2 import Http
from urlparse import parse_qs, urlparse

from django.conf import settings
from django.shortcuts import reverse

from apiclient.discovery import build
from oauth2client.file import Storage
from oauth2client import client

YOUTUBE_READ_WRITE_SCOPE = "https://www.googleapis.com/auth/youtube"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

YOUTUBE_OAUTH_FILE = 'user-oauth2.json'


class ClientSecretCache(object):
    def get(self, name, namespace):
        return {
            "web": {
                "client_id": settings.YOUTUBE_CLIENT_ID,
                "client_secret": settings.YOUTUBE_CLIENT_SECRET,
                "project_id": "dropified-tubehunt",
                "token_uri": "https://www.googleapis.com/oauth2/v3/token",
                "redirect_uris": [
                    "https://app.dropified.com",
                    "https://app.dropified.com/tubehunt/oauth2callback"
                ],
                "javascript_origins": [
                    "https://app.dropified.com"
                ],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs"
            }
        }


class Youtube(object):

    def __init__(self, request):
        self.request = request
        self.base = os.path.join(os.path.dirname(__file__), 'auth/')

    @property
    def storage(self):
        if not hasattr(self, '_storage'):
            self._storage = Storage(os.path.join(self.base, YOUTUBE_OAUTH_FILE))
        return self._storage

    @property
    def credentials(self):
        if not hasattr(self, '_credentials'):
            self._credentials = self.storage.get()

        return self._credentials

    @credentials.setter
    def credentials(self, value):
        self._credentials = value
        self.storage.put(self._credentials)
        self._credentials.set_store(self.storage)

    @property
    def flow(self):
        if not hasattr(self, '_flow'):
            self._flow = client.flow_from_clientsecrets(
                'client_secret',
                cache=ClientSecretCache(),
                scope='https://www.googleapis.com/auth/youtube',
                redirect_uri=self.request.build_absolute_uri(reverse('youtube_ads.views.oauth2callback')))

        return self._flow

    @property
    def client(self):
        if not hasattr(self, '_client'):
            if self.credentials is None or self.credentials.invalid:
                return None

            http_auth = self.credentials.authorize(Http())
            self._client = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, http=http_auth)

        return self._client

    def search(self, query, page=None, related=False):
        kwarg = {
            'part': "id,snippet",
            'type': 'video',
            'maxResults': 50,
        }

        if page is not None:
            kwarg['pageToken'] = page

        channel = re.findall('channel[:/]([^/?]+)', query)

        if len(channel):
            kwarg['channelId'] = channel[0]
            query = 'https://www.youtube.com/channel/{}'.format(kwarg['channelId'])
        else:
            if not related:
                kwarg['q'] = query
            else:
                if 'http' in query:
                    par = parse_qs(urlparse(query).query)
                    kwarg['relatedToVideoId'] = par['v'][0]
                else:
                    kwarg['relatedToVideoId'] = query
                    query = 'https://www.youtube.com/watch?v={}'.format(query)

        search_response = self.client.search().list(**kwarg).execute()
        return search_response, query

    def channels(self, query):
        kwarg = {
            'part': "id,snippet",
            'type': 'channel',
            'maxResults': 50,
            'q': query
        }

        search_response = self.client.search().list(**kwarg).execute()
        return search_response


def get_videos_info(youtube, videos, all_videos=False, count=0):
    data = youtube.videos().list(
        part='id, snippet, contentDetails, statistics',
        id=','.join(videos)
    ).execute()

    videos = []
    for item in data['items']:
        if all_videos or item['contentDetails']['licensedContent']:
            count += 1
            item['statistics']['viewCount'] = "{:,}".format(int(item['statistics'].get('viewCount', 0)))
            item['statistics']['likeCount'] = "{:,}".format(int(item['statistics'].get('likeCount', 0)))
            item['statistics']['dislikeCount'] = "{:,}".format(int(item['statistics'].get('dislikeCount', 0)))
            item['statistics']['commentCount'] = "{:,}".format(int(item['statistics'].get('commentCount', 0)))

            videos.append({
                'snippet': item['snippet'],
                'statistics': item['statistics'],
                'thumbnail': item['snippet']['thumbnails']['medium']['url'],
                'title': item['snippet']['title'],
                'url': 'https://www.youtube.com/watch?v={}'.format(item['id']),
                'id': item['id'],
                'monitized': item['contentDetails']['licensedContent'],
                'index': count
            })

    return videos


def get_channels_info(youtube, channels, count=0):
    data = youtube.channels().list(
        part='id, snippet, statistics',
        id=','.join(channels)
    ).execute()

    channels = []
    for item in data['items']:
        count += 1
        item['statistics']['subscriberCount'] = "{:,}".format(int(item['statistics']['subscriberCount']))
        item['statistics']['videoCount'] = "{:,}".format(int(item['statistics']['videoCount']))
        item['statistics']['viewCount'] = "{:,}".format(int(item['statistics']['viewCount']))
        item['statistics']['commentCount'] = "{:,}".format(int(item['statistics']['commentCount']))

        channels.append({
            'snippet': item['snippet'],
            'statistics': item['statistics'],
            'thumbnail': item['snippet']['thumbnails']['medium']['url'],
            'title': item['snippet']['title'],
            'url': 'https://www.youtube.com/channel/{}'.format(item['id']),
            'id': item['id'],
            'index': count
        })

    return channels
