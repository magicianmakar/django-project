from argparse import FileType

from data_store.models import DataStore
from shopified_core.commands import DropifiedBaseCommand
from shopified_core.utils import using_store_db


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--total', type=int, default=8921927, help='Total number of products in the database')
        parser.add_argument('--products', type=FileType('r'), help='Product ID CSV file')

    def start_command(self, *args, **options):
        steps = 10000
        start = 0

        data_ids = set()

        self.write('Load products')
        for line in options['products']:
            data_ids.add(line.split(',').pop().strip())

        self.progress_total(options['total'])
        entries = using_store_db(DataStore).all()
        while start <= options['total']:
            to_delete = []
            for data in entries[start:start + steps]:
                if data.key not in data_ids:
                    to_delete.append(data.id)

            if to_delete:
                self.write(f'> Delete {len(to_delete)} entires')
                using_store_db(DataStore).filter(id__in=to_delete).delete()

            self.progress_update(steps)

            start += steps
