from django.test import TestCase

from factories import UserFactory, ShopifyStoreFactory

from leadgalaxy.models import *


class UserTestCase(TestCase):
    def setUp(self):
        pass

    def test_userprofile_signal(self):
        user = User.objects.create_user(username='john',
                                        email='john.test@gmail.com',
                                        password='123456')

        self.assertIsNotNone(user.profile)
        self.assertIsNotNone(user.profile.plan)

    def test_userprofile_signal_with_default_plan(self):
        GroupPlan.objects.create(title='Pro Plan', slug='pro-plan', default_plan=0)
        GroupPlan.objects.create(title='Free Plan', slug='free-plan', default_plan=1)

        user = User.objects.create_user(username='john',
                                        email='john.test@gmail.com',
                                        password='123456')

        self.assertIsNotNone(user.profile)
        self.assertIsNotNone(user.profile.plan)

        self.assertEqual(user.profile.plan.slug, 'free-plan')

    def test_add_to_class_decorator(self):
        @add_to_class(User, 'func_test')
        def func_test(self):
            return 'Email: {}'.format(self.email)

        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')

        self.assertTrue(hasattr(User, 'func_test'))
        self.assertTrue(hasattr(user, 'func_test'))
        self.assertEqual(user.func_test(), 'Email: {}'.format(user.email))


class ShopifyStoreTestCase(TestCase):
    def test_must_have_subuser_permissions(self):
        store = ShopifyStoreFactory()
        self.assertEqual(store.subuser_permissions.count(), len(SUBUSER_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = ShopifyStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_permissions.count(), len(SUBUSER_STORE_PERMISSIONS))


class UserProfileTestCase(TestCase):
    def test_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = ShopifyStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.save()
        user.profile.subuser_stores.add(store)
        store_permissions_count = user.profile.subuser_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_STORE_PERMISSIONS))
