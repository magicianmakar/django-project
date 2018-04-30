import datetime
import mock
import time
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone

from last_seen.models import LastSeen, user_seen, clear_interval
from last_seen import settings
from last_seen import middleware


class TestLastSeenModel(TestCase):

    def test_unicode(self):
        user = User(username='testuser')
        ts = datetime.datetime(2013, 1, 1, 2, 3, 4)
        seen = LastSeen(user=user, last_seen=ts)
        self.assertIn('testuser', unicode(seen))
        self.assertIn('2013-01-01 02:03:04', unicode(seen))


class TestLastSeenManager(TestCase):

    @mock.patch('last_seen.models.LastSeen.objects.get_or_create',
                autospec=True)
    def test_seen(self, get_or_create):
        user = User(username='testuser', pk=1)
        lastseen = mock.Mock(LastSeen)
        get_or_create.return_value = (lastseen, True)

        LastSeen.objects.seen(user=user)

        get_or_create.assert_called_with(user=user,
                                         module=settings.LAST_SEEN_DEFAULT_MODULE)
        self.assertFalse(lastseen.save.called)

    @mock.patch('last_seen.models.LastSeen.objects.get_or_create',
                autospec=True)
    def test_seen_no_default(self, get_or_create):
        user = User(username='testuser', pk=1)
        get_or_create.return_value = (None, True)

        LastSeen.objects.seen(user=user, module="test")

        get_or_create.assert_called_with(user=user, module="test")

    @mock.patch('last_seen.models.LastSeen.objects.get_or_create',
                autospec=True)
    def test_seen_create(self, get_or_create):
        user = User(username='testuser')
        lastseen = mock.Mock(LastSeen)
        get_or_create.return_value = (lastseen, True)

        LastSeen.objects.seen(user=user)

        get_or_create.assert_called_with(user=user,
                                         module=settings.LAST_SEEN_DEFAULT_MODULE)
        self.assertFalse(lastseen.save.called)

    @mock.patch('last_seen.models.LastSeen.objects.get_or_create',
                autospec=True)
    def test_seen_update(self, get_or_create):
        user = User(username='testuser')
        lastseen = mock.Mock(LastSeen)
        # force last seen old
        old_time = timezone.now() - \
            datetime.timedelta(seconds=(settings.LAST_SEEN_INTERVAL * 2))
        lastseen.last_seen = old_time
        get_or_create.return_value = (lastseen, False)

        ret = LastSeen.objects.seen(user=user)

        get_or_create.assert_called_with(user=user,
                                         module=settings.LAST_SEEN_DEFAULT_MODULE)
        self.assertTrue(lastseen.save.called)
        self.assertNotEqual(ret.last_seen, old_time)

    @mock.patch('last_seen.models.LastSeen.objects.get_or_create',
                autospec=True)
    def test_seen_update_forced(self, get_or_create):
        user = User(username='testuser')
        lastseen = mock.Mock(LastSeen)
        # force last seen old
        old_time = timezone.now()
        lastseen.last_seen = old_time
        get_or_create.return_value = (lastseen, False)

        ret = LastSeen.objects.seen(user=user, force=True)

        get_or_create.assert_called_with(user=user,
                                         module=settings.LAST_SEEN_DEFAULT_MODULE)
        self.assertTrue(lastseen.save.called)
        self.assertNotEqual(ret.last_seen, old_time)

    @mock.patch('last_seen.models.LastSeen.objects.get_or_create',
                autospec=True)
    def test_seen_found_not_updated(self, get_or_create):
        user = User(username='testuser')
        lastseen = mock.Mock(LastSeen)
        # force last seen old
        old_time = timezone.now()
        lastseen.last_seen = old_time
        get_or_create.return_value = (lastseen, False)

        ret = LastSeen.objects.seen(user=user)

        get_or_create.assert_called_with(user=user,
                                         module=settings.LAST_SEEN_DEFAULT_MODULE)
        self.assertFalse(lastseen.save.called)
        self.assertEqual(ret.last_seen, old_time)

    def test_when_non_existent(self):
        user = User(username='testuser', pk=1)
        self.assertRaises(LastSeen.DoesNotExist, LastSeen.objects.when, user)

    @mock.patch('last_seen.models.LastSeen.objects.filter')
    def test_seen_defaults(self, filter):
        user = User(username='testuser')
        LastSeen.objects.when(user=user)

        filter.assert_called_with(user=user)

    @mock.patch('last_seen.models.LastSeen.objects.filter')
    def test_seen_module(self, filter):
        user = User(username='testuser')
        LastSeen.objects.when(user=user, module='mod')

        filter.assert_called_with(user=user, module='mod')

    @mock.patch('last_seen.models.LastSeen.objects.filter')
    def test_seen_site(self, filter):
        user = User(username='testuser')
        LastSeen.objects.when(user=user)

        filter.assert_called_with(user=user)


class TestUserSeen(TestCase):

    def setUp(self):
        cache.delete_pattern('last_seen:*')

    @mock.patch('last_seen.models.LastSeen.objects.seen')
    def test_user_seen(self, seen):
        user = User(username='testuser', pk=999)

        user_seen(user)
        seen.assert_called_with(user, module=settings.LAST_SEEN_DEFAULT_MODULE, interval=settings.LAST_SEEN_INTERVAL)

    @mock.patch('last_seen.models.LastSeen.objects.seen')
    def test_user_seen_no_default(self, seen):
        user = User(username='testuser', pk=1)
        user_seen(user, module="test")
        seen.assert_called_with(user, module="test", interval=settings.LAST_SEEN_INTERVAL)

    @mock.patch('last_seen.models.LastSeen.objects.seen')
    def test_user_seen_cached(self, seen):
        user = User(username='testuser', pk=1)
        module = 'test_mod'
        cache.set("last_seen:%s:%s" % (module, user.pk), time.time())
        user_seen(user, module=module)
        self.assertFalse(seen.called)

    @mock.patch('last_seen.models.LastSeen.objects.seen')
    def test_user_seen_cache_expired(self, seen):
        user = User(username='testuser', pk=1)
        module = 'test_mod'
        cache.set("last_seen:%s:%s" % (module, user.pk),
                  time.time() - (2 * settings.LAST_SEEN_INTERVAL))
        user_seen(user, module=module)
        seen.assert_called_with(user, module=module, interval=settings.LAST_SEEN_INTERVAL)


class TestClearInterval(TestCase):
    def setUp(self):
        cache.delete_pattern('last_seen:*')

    @mock.patch('last_seen.models.LastSeen.objects.filter')
    @mock.patch('last_seen.models.cache')
    def test_clear_interval(self, cache, filter):
        user = User(username='testuser', pk=1)
        ls1 = LastSeen(user=user, module="mod1")
        ls2 = LastSeen(user=user, module="mod2")
        filter.return_value = [ls1, ls2]

        clear_interval(user)

        filter.assert_called_with(user=user)
        expected = {'last_seen:mod1:1': -1, 'last_seen:mod2:1': -1}
        cache.set_many.assert_called_with(expected)

    @mock.patch('last_seen.models.LastSeen.objects.filter')
    @mock.patch('last_seen.models.cache')
    def test_clear_interval_none(self, cache, filter):
        user = User(username='testuser', pk=1)
        filter.return_value = []

        clear_interval(user)

        filter.assert_called_with(user=user)
        self.assertFalse(cache.delete_many.called)

    def test_clear_interval_works(self):
        user = User.objects.create(username='testuser')

        user_seen(user)
        when1 = LastSeen.objects.when(user=user)
        clear_interval(user)
        user_seen(user)
        when2 = LastSeen.objects.when(user=user)

        self.assertNotEqual(when1, when2)


class TestMiddleware(TestCase):

    middleware = middleware.LastSeenMiddleware()

    @mock.patch('last_seen.middleware.user_seen')
    def test_process_request(self, user_seen):
        request = mock.Mock()
        request.user.is_authenticated.return_value = False
        self.middleware.process_request(request)
        self.assertFalse(user_seen.called)

    @mock.patch('last_seen.middleware.user_seen')
    def test_process_request_auth(self, user_seen):
        request = mock.Mock()
        request.path = ''
        request.session = {}
        request.user.is_authenticated.return_value = True
        request.user.is_subuser = False
        self.middleware.process_request(request)
        user_seen.assert_called_with(request.user.models_user, module=None)
