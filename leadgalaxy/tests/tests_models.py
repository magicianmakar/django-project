from django.test import TestCase

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
