from leadgalaxy.tests.factories import AppPermissionFactory, GroupPlanFactory, UserFactory
from lib.test import BaseTestCase

from ..utils import user_can_download_label
from .factories import PLSupplementFactory, UserSupplementFactory, UserSupplementLabelFactory


class TestUserCanDownloadLabel(BaseTestCase):
    def test_owner_can_dowload_label(self):
        user = UserFactory()
        pl_supplement = PLSupplementFactory()
        user_supplement = UserSupplementFactory(user=user, pl_supplement=pl_supplement)
        label = UserSupplementLabelFactory(user_supplement=user_supplement)
        self.assertTrue(user_can_download_label(user, label))

    def test_others_cant_dowload_label(self):
        user = UserFactory()
        pl_supplement = PLSupplementFactory()
        user_supplement = UserSupplementFactory(user=UserFactory(), pl_supplement=pl_supplement)
        label = UserSupplementLabelFactory(user_supplement=user_supplement)
        self.assertFalse(user_can_download_label(user, label))

    def test_pls_staff_can_download_label(self):
        plan = GroupPlanFactory()
        plan.permissions.add(AppPermissionFactory(name='pls_staff.use'))
        user = UserFactory()
        user.profile.plan = plan
        user.profile.save()
        pl_supplement = PLSupplementFactory()
        user_supplement = UserSupplementFactory(user=UserFactory(), pl_supplement=pl_supplement)
        label = UserSupplementLabelFactory(user_supplement=user_supplement)
        self.assertTrue(user_can_download_label(user, label))

    def test_pls_admin_can_download_label(self):
        plan = GroupPlanFactory()
        plan.permissions.add(AppPermissionFactory(name='pls_admin.use'))
        user = UserFactory()
        user.profile.plan = plan
        user.profile.save()
        pl_supplement = PLSupplementFactory()
        user_supplement = UserSupplementFactory(user=UserFactory(), pl_supplement=pl_supplement)
        label = UserSupplementLabelFactory(user_supplement=user_supplement)
        self.assertTrue(user_can_download_label(user, label))
