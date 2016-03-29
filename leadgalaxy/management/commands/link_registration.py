from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone

import requests

from leadgalaxy.models import *
from leadgalaxy import utils


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--unregistered', dest='unregistered',
                            action='store_false', help='Show Unregistered Emails')

    def handle(self, *args, **options):
        registartions = PlanRegistration.objects.filter(expired=False).exclude(plan=None).exclude(email='')
        for reg in registartions:
            if reg.get_usage_count() is not None:
                continue

            try:
                user = User.objects.get(email__iexact=reg.email)
            except User.DoesNotExist:
                if options['unregistered']:
                    print 'Not Registred|{}|{}|{}'.format(reg.email, reg.plan.title, str(reg.created_at).split(' ')[0])
                continue
            except:
                print 'WARNING: Get Email Exception for:', reg.email
                continue

            profile = user.profile
            print 'Change user {} ({}) Plan from {} to {}'.format(user.username, user.email, profile.plan.title, reg.plan.title)

            self.apply_plan_registrations(profile, reg)

        registartions = PlanRegistration.objects.filter(expired=False).exclude(bundle=None).exclude(email='')
        for reg in registartions:
            if not reg.bundle or reg.get_usage_count() is not None:
                continue

            try:
                user = User.objects.get(email__iexact=reg.email)
            except User.DoesNotExist:
                if options['unregistered']:
                    print 'Not Registred|{}|{}|{}'.format(reg.email, reg.bundle.title, str(reg.created_at).split(' ')[0])
                continue

            profile = user.profile
            print 'Add Bundle: {} for: {} ({})'.format(reg.bundle.title, user.username, user.email)

            profile.bundles.add(reg.bundle)
            reg.user = user
            reg.expired = True
            reg.save()

            profile.save()

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
