from lib.test import BaseTestCase

from leadgalaxy.tests.factories import (
    UserFactory,
    ShopifyStoreFactory,
    AppPermissionFactory
)

from ..models import VideosList
from .factories import VideosListFactory


class TubeHuntApiTest(BaseTestCase):
    def setUp(self):
        self.parent_user = UserFactory()
        self.user = UserFactory()
        self.password = 'test'
        self.user.set_password(self.password)
        self.user.save()
        self.store = ShopifyStoreFactory(user=self.user)
        self.permission = AppPermissionFactory(name='youtube_ads.use')

    def test_must_be_logged_in_to_get_video_list(self):
        r = self.client.get('/api/tubehunt/video-lists')
        self.assertEqual(r.status_code, 401)

    def test_must_return_video_list(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.get('/api/tubehunt/video-lists')
        self.assertIn('lists', r.json())

    def test_must_be_logged_in_to_post_video_list(self):
        r = self.client.post('/api/tubehunt/video-list', {})
        self.assertEqual(r.status_code, 401)

    def test_must_have_permission_to_post_video_list(self):
        self.client.login(username=self.user.username, password=self.password)
        r = self.client.post('/api/tubehunt/video-list', {})
        self.assertIn('Permission Denied', r.json()['error'])

    def test_must_create_video_list(self):
        self.client.login(username=self.user.username, password=self.password)
        self.user.profile.plan.permissions.add(self.permission)
        count = self.user.videoslist_set.count()
        data = {'newListTitle': 'test', 'selected': 'a;b;c'}
        self.client.post('/api/tubehunt/video-list', data)
        new_count = self.user.videoslist_set.count()
        self.assertEqual(count + 1, new_count)

    def test_must_return_created_video_list_id(self):
        self.client.login(username=self.user.username, password=self.password)
        self.user.profile.plan.permissions.add(self.permission)
        data = {'newListTitle': 'test', 'selected': 'a;b;c'}
        r = self.client.post('/api/tubehunt/video-list', data)
        video_list = self.user.videoslist_set.first()
        self.assertEqual(video_list.pk, r.json()['id'])

    def test_must_update_video_list(self):
        self.client.login(username=self.user.username, password=self.password)
        self.user.profile.plan.permissions.add(self.permission)
        video_list = VideosListFactory(user=self.user)
        data = {'selected': 'a;b;c', 'selectedList': video_list.pk}
        r = self.client.post('/api/tubehunt/video-list', data)
        self.assertEqual(video_list.pk, r.json()['id'])

    def test_must_create_video_list_if_title_is_present(self):
        self.client.login(username=self.user.username, password=self.password)
        self.user.profile.plan.permissions.add(self.permission)
        video_list = VideosListFactory(user=self.user)
        count = self.user.videoslist_set.count()
        data = {'newListTitle': 'test', 'selected': 'a;b;c', 'selectedList': video_list.pk}
        self.client.post('/api/tubehunt/video-list', data)
        new_count = self.user.videoslist_set.count()
        self.assertEqual(count + 1, new_count)

    def test_must_be_logged_in_to_delete_video_list(self):
        video_list = VideosListFactory(user=self.user)
        r = self.client.get('/api/tubehunt/video-lists?list_id={}'.format(video_list.pk))
        self.assertEqual(r.status_code, 401)

    def test_must_delete_video_list(self):
        self.client.login(username=self.user.username, password=self.password)
        video_list = VideosListFactory(user=self.user)
        self.client.delete('/api/tubehunt/video-list?list_id={}'.format(video_list.pk))
        with self.assertRaises(VideosList.DoesNotExist):
            VideosList.objects.get(pk=video_list.pk)

    def test_must_be_logged_in_to_delete_list_video(self):
        video_list = VideosListFactory(user=self.user)
        video_list.add_videos('a;b;c')
        video_list.save()
        r = self.client.delete('/api/tubehunt/list-video?list_id={}&video_id={}'.format(video_list.pk, 'b'))
        self.assertEqual(r.status_code, 401)

    def test_must_delete_video_from_video_list(self):
        self.client.login(username=self.user.username, password=self.password)
        video_list = VideosListFactory(user=self.user)
        video_list.add_videos('a;b;c')
        video_list.save()
        self.client.delete('/api/tubehunt/list-video?list_id={}&video_id={}'.format(video_list.pk, 'b'))
        video_list.refresh_from_db()
        self.assertNotIn('b', video_list.get_videos())

    def test_must_be_logged_in_to_delete_list_videos(self):
        video_list = VideosListFactory(user=self.user)
        video_list.add_videos('a;b;c')
        video_list.save()
        values = video_list.pk, 'b', 'c'
        r = self.client.delete('/api/tubehunt/list-videos?list_id={}&video_ids={}&video_ids={}'.format(*values))
        self.assertEqual(r.status_code, 401)

    def test_must_delete_videos_from_video_list(self):
        self.client.login(username=self.user.username, password=self.password)
        video_list = VideosListFactory(user=self.user)
        video_list.add_videos('a;b;c')
        video_list.save()
        values = video_list.pk, 'b', 'c'
        self.client.delete('/api/tubehunt/list-videos?list_id={}&video_ids[]={}&video_ids[]={}'.format(*values))
        video_list.refresh_from_db()
        self.assertNotIn('b', video_list.get_videos())
        self.assertNotIn('c', video_list.get_videos())
