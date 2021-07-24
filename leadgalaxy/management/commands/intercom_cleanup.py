import traceback
from queue import Queue
from threading import Thread

import requests

from django.conf import settings
from shopified_core.commands import DropifiedBaseCommand


class ImportException(Exception):
    pass


def worker(q, cmd):
    while True:
        user = q.get()

        cmd.progress_update()

        cmd.write(f'Delete for {user["email"]}')

        try:
            r = requests.delete(
                url=f"https://api.intercom.io/contacts/{user['id']}",
                headers={
                    'Authorization': f'Bearer {settings.INTERCOM_ACCESS_TOKEN}',
                    'Accept': 'application/json'
                })

            r.raise_for_status()
        except Exception:
            cmd.write(f'Error for {user["id"]}')
            traceback.print_exc()

        q.task_done()


class Command(DropifiedBaseCommand):

    def start_command(self, *args, **options):
        q = Queue()
        for i in range(10):
            t = Thread(target=worker, args=(q, self))
            t.daemon = True
            t.start()

        for user in list(self.get_users_to_delete()):
            q.put(user)

        q.join()

    def get_users_to_delete(self):
        self.total = 0
        self.pagination = {"per_page": 150}
        while True:
            try:
                r = requests.post(
                    url="https://api.intercom.io/contacts/search",
                    headers={
                        'Authorization': f'Bearer {settings.INTERCOM_ACCESS_TOKEN}',
                        'Accept': 'application/json'
                    }, json={
                        "query": {
                            "operator": "AND",
                            "value": [
                                {"field": "has_hard_bounced", "operator": "=", "type": "boolean", "value": True},
                                # {"field": "last_replied_at", "operator": "=", "type": "date", "value": None}
                            ]
                        },
                        **self.pagination
                    })

                r.raise_for_status()

                if not self.total:
                    self.total = r.json()['total_count']
                    self.progress_total(self.total)

                self.write(f"==> Page  {r.json()['pages']['page']}")
                for i in (r.json()['data']):
                    yield i

                try:
                    self.pagination = {"pagination": {
                        "per_page": 150,
                        "starting_after": r.json()['pages']['next']['starting_after']
                    }
                    }
                except:
                    break
            except KeyboardInterrupt:
                raise
            except:
                traceback.print_exc()
