from lib.test import BaseTestCase

from leadgalaxy.models import PlanRegistration
from leadgalaxy.tests.factories import (
    UserFactory,
    AppPermissionFactory,
    PlanRegistrationFactory,
    GroupPlanFactory
)


class SubusersApiTest(BaseTestCase):
    def setUp(self):
        password = 'test'
        self.user = UserFactory()
        self.user.set_password(password)
        self.user.save()

        self.subuser = UserFactory(email='subuser@dropified.com')
        self.subuser.profile.subuser_parent = self.user
        self.subuser.profile.save()

        self.permission = AppPermissionFactory(name='sub_users.use')
        self.user.profile.plan.permissions.add(self.permission)

        self.client.login(username=self.user.username, password=password)

        GroupPlanFactory(register_hash='606bd8eb8cb148c28c4c022a43f0432d', slug='free-plan')
        GroupPlanFactory(slug='subuser-plan')

    def test_user_without_permission(self):
        self.user.profile.plan.permissions.remove(self.permission)
        r = self.client.delete('/api/subusers/invite')
        self.assertIn('Permission Denied', r.json()['error'])
        self.assertEqual(r.status_code, 403)

    def test_delete_invite(self):
        reg = PlanRegistrationFactory(sender=self.user)

        r = self.client.delete(f'/api/subusers/invite?invite={reg.id}')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(PlanRegistration.objects.exists())

        # Not found
        r = self.client.delete('/api/subusers/invite?invite=12345')
        self.assertEqual(r.status_code, 500)

    def test_post_delete(self):
        data = {
            'subuser': self.subuser.id
        }

        # Subuser not found
        r = self.client.post('/api/subusers/delete', {'subuser': '12345'})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()['error'], 'User not found')

        r = self.client.post('/api/subusers/delete', data)
        self.assertEqual(r.status_code, 200)

        self.subuser.refresh_from_db()
        self.subuser.profile.refresh_from_db()
        self.assertIsNone(self.subuser.profile.subuser_parent)
        self.assertEqual(self.subuser.profile.subuser_stores.count(), 0)
        self.assertEqual(self.subuser.profile.subuser_chq_stores.count(), 0)
        self.assertTrue(self.subuser.profile.plan.is_free)

    def test_post_invite(self):
        r = self.client.post('/api/subusers/invite', {'email': 'subuser@subuser'})
        self.assertEqual(r.status_code, 501)
        self.assertEqual(r.json()['error'], 'Email is not valid')

        r = self.client.post('/api/subusers/invite', {'email': self.subuser.email})
        self.assertEqual(r.status_code, 501)
        self.assertIn('already registered', r.json()['error'])

        PlanRegistrationFactory(sender=self.user, email='subuser2@dropified.com')
        r = self.client.post('/api/subusers/invite', {'email': 'subuser2@dropified.com'})
        self.assertEqual(r.status_code, 501)
        self.assertIn('already sent', r.json()['error'])

        r = self.client.post('/api/subusers/invite', {'email': 'subuser3@dropified.com'})
        self.assertEqual(r.status_code, 200)

        reg = PlanRegistration.objects.get(email='subuser3@dropified.com')
        self.assertEqual(reg.plan.slug, 'subuser-plan')
        self.assertEqual(reg.sender.email, self.user.email)
