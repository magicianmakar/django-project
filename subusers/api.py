from django.views.generic import View
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from lib.exceptions import capture_message

from leadgalaxy.forms import EmailForm
from leadgalaxy.models import PlanRegistration, AccessToken
from leadgalaxy.utils import get_plan, generate_plan_registration
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import send_email_from_template


class SubusersApi(ApiResponseMixin, View):
    def delete_invite(self, request, user, data):
        if not user.can('sub_users.use'):
            raise PermissionDenied('Sub User Invite')

        PlanRegistration.objects.get(id=data.get('invite'), sender=user).delete()

        return self.api_success()

    def post_delete(self, request, user, data):
        try:
            subuser = User.objects.get(id=data.get('subuser'), profile__subuser_parent=user)
        except User.DoesNotExist:
            return self.api_error('User not found', status=404)
        except:
            return self.api_error('Unknown Error', status=500)

        profile = subuser.profile

        profile.subuser_parent = None
        profile.subuser_stores.clear()
        profile.subuser_chq_stores.clear()
        profile.plan = get_plan(plan_hash='606bd8eb8cb148c28c4c022a43f0432d')
        profile.save()

        AccessToken.objects.filter(user=subuser).delete()

        return self.api_success()

    def post_invite(self, request, user, data):
        if not user.can('sub_users.use'):
            raise PermissionDenied('Sub User Invite')

        subuser_email = data.get('email', '').strip()

        if not EmailForm({'email': subuser_email}).is_valid():
            return self.api_error('Email is not valid', status=501)

        users = User.objects.filter(email__iexact=subuser_email)
        if users.count():
            if users.count() == 1:
                subuser = users.first()
                if subuser.profile.plan.is_free and not user.models_user.get_config('_limit_subusers_invite'):
                    plan = get_plan(plan_slug='subuser-plan')
                    reg = generate_plan_registration(plan=plan, sender=user, data={
                        'email': subuser_email,
                        'auto': True
                    })

                    subuser.profile.apply_registration(reg)

                    data = {
                        'sender': user,
                    }

                    send_email_from_template(
                        tpl='subuser_added.html',
                        subject='Invitation to join Dropified',
                        recipient=subuser_email,
                        data=data,
                    )

                    return self.api_success({
                        'hash': reg.register_hash
                    })

            return self.api_error('Email is is already registered to an account', status=501)

        if PlanRegistration.objects.filter(email__iexact=subuser_email).count():
            return self.api_error('An Invitation is already sent to this email', status=501)

        if user.models_user.get_config('_limit_subusers_invite'):
            capture_message('Sub User Invite Attempts', level='warning')
            return self.api_error('Server Error', status=501)

        plan = get_plan(plan_slug='subuser-plan')
        reg = generate_plan_registration(plan=plan, sender=user, data={
            'email': subuser_email
        })

        data = {
            'email': subuser_email,
            'sender': user,
            'reg_hash': reg.register_hash
        }

        send_email_from_template(
            tpl='subuser_invite.html',
            subject='Invitation to join Dropified',
            recipient=subuser_email,
            data=data,
        )

        return self.api_success({
            'hash': reg.register_hash
        })
