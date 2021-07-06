from django.contrib.auth.models import User

from leadgalaxy.utils import generate_user_activity
from shopified_core.commands import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Generate user activity log'

    def add_arguments(self, parser):
        parser.add_argument('user', type=str, help='User Email or ID')

    def start_command(self, *args, **options):
        user_id = options['user']

        try:
            user = User.objects.get(id=int(user_id))
        except ValueError:
            user = User.objects.get(email__iexact=user_id)

        self.write(f'Activity log for {user.email}')
        url = generate_user_activity(user, output=self)

        self.write(f'Log URL: {url}')
