from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone

import requests

from leadgalaxy.models import *
from leadgalaxy import utils


class Command(BaseCommand):
    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        registartions = PlanRegistration.objects.filter(expired=False).exclude(plan=None).exclude(email='')
        for reg in registartions:
            if reg.get_usage_count() is not None:
                continue

            try:
                user = User.objects.get(email__iexact=reg.email)
            except User.DoesNotExist:
                print 'Not registred yet:', reg.email
                continue

            profile = user.profile
            print 'Change user {} Plan from {} to {}'.format(user.username, profile.plan.title, reg.plan.title)

            self.apply_plan_registrations(profile, reg)

    def apply_plan_registrations(self, profile, registration):
        profile.plan = registration.plan

        registration.expired = True
        registration.user = profile.user
        registration.save()

        # Process other purchases (like additional bundles)
        purchases = PlanRegistration.objects.filter(email__iexact=profile.user.email) \
                                            .filter(expired=False) \
                                            .exclude(id=registration.id)

        for p in purchases:
            if not p.bundle:
                continue

            print ' + Add Bundle:', p.bundle.title

            profile.bundles.add(p.bundle)
            p.user = profile.user
            p.expired = True
            p.save()

        profile.save()
