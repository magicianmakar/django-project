from unittest.mock import Mock, patch, PropertyMock

import arrow

from django.core.cache import cache

from .factories import UserFactory, ShopifyStoreFactory, GroupPlanFactory

from lib.test import BaseTestCase
from leadgalaxy.utils import create_user_without_signals
from shopified_core.decorators import add_to_class
from shopify_orders.models import MAX_LOGS, ShopifyOrderLog
from leadgalaxy.models import (
    SUBUSER_PERMISSIONS,
    SUBUSER_STORE_PERMISSIONS,
    GroupPlan,
    SubuserPermission,
    User,
)
from .factories import ShopifyOrderLogFactory

from stripe_subscription.models import StripeCustomer
from stripe_subscription.tests.factories import StripeCustomerFactory


class UserTestCase(BaseTestCase):
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

    def test_userprofile_signal_disconnect(self):
        _user, _profile = create_user_without_signals(
            username='john2',
            email='john.test2@gmail.com',
            password='123456')

        self.assertEqual(_user.profile, _profile)
        self.assertIsNotNone(_user.profile)
        self.assertIsNone(_user.profile.plan)

        user = User.objects.create_user(username='john',
                                        email='john.test@gmail.com',
                                        password='123456')

        self.assertIsNotNone(user.profile)
        self.assertIsNotNone(user.profile.plan)

    def test_add_to_class_decorator(self):
        @add_to_class(User, 'func_test')
        def func_test(self):
            return 'Email: {}'.format(self.email)

        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')

        self.assertTrue(hasattr(User, 'func_test'))
        self.assertTrue(hasattr(user, 'func_test'))
        self.assertEqual(user.func_test(), 'Email: {}'.format(user.email))


class ShopifyStoreTestCase(BaseTestCase):
    def test_must_have_subuser_permissions(self):
        store = ShopifyStoreFactory()
        self.assertEqual(store.subuser_permissions.count(), len(SUBUSER_STORE_PERMISSIONS))

    def test_must_add_subuser_permissions_on_create_only(self):
        store = ShopifyStoreFactory()
        store.title = 'Updated title'
        store.save()
        self.assertEqual(store.subuser_permissions.count(), len(SUBUSER_STORE_PERMISSIONS))


class UserProfileTestCase(BaseTestCase):
    def tearDown(self):
        cache.clear()

    def test_subusers_must_have_all_store_permissions_when_assigned_a_store(self):
        parent_user = UserFactory()
        store = ShopifyStoreFactory(user=parent_user)
        user = UserFactory()
        user.profile.subuser_parent = parent_user
        user.profile.save()
        user.profile.subuser_stores.add(store)
        store_permissions_count = user.profile.subuser_permissions.filter(store=store).count()
        self.assertEqual(store_permissions_count, len(SUBUSER_STORE_PERMISSIONS))

    def test_subusers_must_have_global_permissions_when_created(self):
        parent_user = UserFactory()
        plan = GroupPlanFactory(title='Subuser Plan', slug='subuser-plan')
        registration = Mock()
        registration.plan = plan
        registration.sender = parent_user
        registration.get_data = Mock(return_value={})
        registration.bundle = None
        user = UserFactory()
        user.profile.apply_registration(registration)
        permissions_count = user.profile.subuser_permissions.count()
        if SubuserPermission.objects.count():
            self.assertEqual(permissions_count, len(SUBUSER_PERMISSIONS))

    def test_user_on_trial_default_is_false(self):
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.profile.plan = GroupPlanFactory(payment_gateway='new')
        user.profile.save()
        self.assertFalse(user.profile.on_trial)

    def test_shopify_user_on_trial_if_subscription_on_trial(self):
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.profile.plan = GroupPlanFactory(payment_gateway='shopify')
        user.profile.save()
        subscription = Mock(on_trial=True)
        user.profile.get_current_shopify_subscription = Mock(return_value=subscription)
        self.assertTrue(user.profile.on_trial)

    def test_shopify_user_not_on_trial_if_subscription_not_on_trial(self):
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.profile.plan = GroupPlanFactory(payment_gateway='shopify')
        user.profile.save()
        subscription = Mock(on_trial=False)
        user.profile.get_current_shopify_subscription = Mock(return_value=subscription)
        self.assertFalse(user.profile.on_trial)

    @patch('stripe_subscription.models.StripeCustomer.on_trial', PropertyMock(return_value=True))
    def test_stripe_user_on_trial_if_subscription_on_trial(self):
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.profile.plan = GroupPlanFactory(payment_gateway='stripe')
        user.profile.save()
        user.stripe_customer = StripeCustomerFactory()
        self.assertTrue(user.profile.on_trial)

    @patch('stripe_subscription.models.StripeCustomer.on_trial', PropertyMock(return_value=False))
    def test_stripe_user_not_on_trial_if_subscription_not_on_trial(self):
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.profile.plan = GroupPlanFactory(payment_gateway='stripe')
        user.profile.save()
        user.stripe_customer = StripeCustomerFactory()
        self.assertFalse(user.profile.on_trial)

    def test_user_trial_days_left_default_is_zero(self):
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.profile.plan = GroupPlanFactory(payment_gateway='new')
        user.profile.save()
        self.assertEquals(user.profile.trial_days_left, 0)

    def test_shopify_user_trial_days_left(self):
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.profile.plan = GroupPlanFactory(payment_gateway='shopify')
        user.profile.save()
        trial_days_left = 14
        subscription = Mock(trial_days_left=trial_days_left)
        user.profile.get_current_shopify_subscription = Mock(return_value=subscription)
        self.assertEquals(user.profile.trial_days_left, trial_days_left)

    def test_stripe_user_trial_days_left(self):
        user = User.objects.create_user(username='john', email='john.test@gmail.com', password='123456')
        user.profile.plan = GroupPlanFactory(payment_gateway='stripe')
        user.profile.save()
        trial_days_left = 14
        with patch.object(StripeCustomer, 'trial_days_left', PropertyMock(return_value=trial_days_left)):
            user.stripe_customer = StripeCustomerFactory()
            self.assertEquals(user.profile.trial_days_left, trial_days_left)


class ShopifyOrderLogTestCase(BaseTestCase):
    def test_create_log(self):
        log = ShopifyOrderLogFactory()

        log2 = ShopifyOrderLog.objects.create(store=log.store, order_id=log.order_id)
        self.assertIsNotNone(log2.update_count)
        self.assertEqual(log2.update_count, 0)

    def test_add_log(self):
        log = ShopifyOrderLogFactory()
        self.assertTrue(log.order_id)
        self.assertTrue(log.store.id)

        data = {
            "order_id": log.order_id,
            "line_id": 77788885,
            "store": log.store,
            "user": log.store.user,
            "log": 'Manually Fulfilled in Shopify',
            'log_time': arrow.utcnow().timestamp
        }

        log = ShopifyOrderLog.objects.update_order_log(**data)
        self.assertEqual(len(log.get_logs()), 1)

        # Adds duplicate entries
        log = ShopifyOrderLog.objects.update_order_log(**data)
        self.assertEqual(len(log.get_logs()), 2)

        # max number of entries is MAX_LOGS
        tries = 100
        for i in range(1, tries):
            data['log'] = f'Order Number is: {i}'
            data['log_time'] += 1
            log = ShopifyOrderLog.objects.update_order_log(**data)

            self.assertEqual(len(log.get_logs()), min(2 + i, MAX_LOGS))

        for i in range(1, MAX_LOGS):
            self.assertEqual(f'Order Number is: {tries - i}', log.get_logs()[i - 1]['log'])

        self.assertLessEqual(len(log.get_logs()), MAX_LOGS)
        self.assertGreaterEqual(log.update_count, 100)
