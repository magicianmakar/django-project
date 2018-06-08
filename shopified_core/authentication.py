from leadgalaxy.models import AccessToken
from rest_framework import authentication, exceptions


class TokenAuthentication(authentication.TokenAuthentication):
    model = AccessToken

    def authenticate_credentials(self, key):
        try:
            token = self.model.objects.get(token=key)
        except self.model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token')

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted')

        return (token.user, token)

    def authenticate_header(self, request):
        return 'Token'
