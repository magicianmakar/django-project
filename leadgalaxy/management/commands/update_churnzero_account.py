import traceback
from queue import Queue
from threading import Thread

from shopified_core.management import DropifiedBaseCommand
from django.contrib.auth.models import User
from churnzero_core.utils import set_churnzero_account


def worker(q, cmd):
    while True:
        item = q.get()

        cmd.progress_update()

        try:
            set_churnzero_account(item['user'])
        except Exception:
            cmd.write(f'Error for {item["user"].email}')
            traceback.print_exc()

        q.task_done()


class Command(DropifiedBaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--progress', action='store_true', help='Show Update Progress')

    def start_command(self, progress, *args, **options):
        users = User.objects.filter(profile__subuser_parent__isnull=True)
        self.progress_total(users.count(), progress)

        q = Queue()
        for i in range(40):
            t = Thread(target=worker, args=(q, self))
            t.daemon = True
            t.start()

        for user in users:
            q.put({
                'user': user,
            })

        q.join()
