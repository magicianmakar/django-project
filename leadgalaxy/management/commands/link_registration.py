from django.contrib.auth.models import User

from shopified_core.commands import DropifiedBaseCommand
from leadgalaxy.models import PlanRegistration

from lib.exceptions import capture_exception


class Command(DropifiedBaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--unregistered', dest='unregistered',
                            action='store_true', help='Show Unregistered Emails')

    def start_command(self, *args, **options):
        registartions = PlanRegistration.objects.filter(expired=False).exclude(plan=None).exclude(email='')
        for reg in registartions:
            if reg.get_usage_count() is not None:
                continue

            try:
                user = User.objects.get(email__iexact=reg.email)
            except User.DoesNotExist:
                if options['unregistered']:
                    self.stdout.write('Not Registred|{}|{}|{}'.format(
                        reg.email, reg.plan.title, str(reg.created_at).split(' ')[0]))
                continue
            except:
                self.stdout.write('WARNING: Get Email Exception for: {}'.format(reg.email), self.style.WARNING)
                capture_exception()
                continue

            profile = user.profile
            self.stdout.write('Change user {} ({}) Plan from {} to {}'.format(
                user.username, user.email, profile.plan.title, reg.plan.title), self.style.SUCCESS)

            self.apply_plan_registrations(profile, reg)

        registartions = PlanRegistration.objects.filter(expired=False).exclude(bundle=None).exclude(email='')
        for reg in registartions:
            if not reg.bundle or reg.get_usage_count() is not None:
                continue

            try:
                user = User.objects.get(email__iexact=reg.email)
            except User.DoesNotExist:
                if options['unregistered']:
                    self.stdout.write('Not Registred|{}|{}|{}'.format(
                        reg.email, reg.bundle.title, str(reg.created_at).split(' ')[0]))
                continue

            profile = user.profile
            self.stdout.write('Add Bundle: {} for: {} ({})'.format(
                reg.bundle.title, user.username, user.email), self.style.SUCCESS)

            profile.bundles.add(reg.bundle)
            reg.user = user
            reg.expired = True
            reg.save()

            profile.save()

    def apply_plan_registrations(self, profile, registration):
        profile.apply_registration(registration)

        # Process other purchases (like additional bundles)
        purchases = PlanRegistration.objects.filter(email__iexact=profile.user.email) \
                                            .filter(expired=False) \
                                            .exclude(id=registration.id)

        for p in purchases:
            if not p.bundle:
                continue

            self.stdout.write(' + Add Bundle: {}'.format(p.bundle.title))
            profile.apply_registration(p)
