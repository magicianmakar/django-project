from leadgalaxy.tests.factories import AppPermissionFactory, GroupPlanFactory, UserFactory
from lib.test import BaseTestCase

from ..utils import user_can_download_label
from .factories import PLSupplementFactory, UserSupplementFactory, UserSupplementLabelFactory


class TestUserCanDownloadLabel(BaseTestCase):
    def setUp(self):
        self.user = UserFactory()
        self.user.profile.unique_supplements = -1
        self.user.profile.user_supplements = -1
        self.user.profile.save()

        pl_supplement = PLSupplementFactory()
        self.user_supplement = UserSupplementFactory(user=self.user, pl_supplement=pl_supplement)

    def test_owner_can_dowload_label(self):
        label = UserSupplementLabelFactory(user_supplement=self.user_supplement)
        self.assertTrue(user_can_download_label(self.user, label))

    def test_others_cant_dowload_label(self):
        label = UserSupplementLabelFactory(user_supplement=self.user_supplement)
        self.assertFalse(user_can_download_label(UserFactory(), label))

    def test_pls_staff_can_download_label(self):
        plan = GroupPlanFactory()
        plan.permissions.add(AppPermissionFactory(name='pls_staff.use'))
        staff_user = UserFactory()
        staff_user.profile.plan = plan
        staff_user.profile.save()

        label = UserSupplementLabelFactory(user_supplement=self.user_supplement)
        self.assertTrue(user_can_download_label(staff_user, label))

    def test_pls_admin_can_download_label(self):
        plan = GroupPlanFactory()
        plan.permissions.add(AppPermissionFactory(name='pls_admin.use'))
        staff_user = UserFactory()
        staff_user.profile.plan = plan
        staff_user.profile.save()

        label = UserSupplementLabelFactory(user_supplement=self.user_supplement)
        self.assertTrue(user_can_download_label(staff_user, label))
