import simplejson as json

from shopified_core.commands import DropifiedBaseCommand
from supplements.models import PLSupplement


class Command(DropifiedBaseCommand):
    help = 'Create json for PLSupplements'

    def start_command(self, *args, **options):
        data_list = []
        for supplement in PLSupplement.objects.all():
            data_list.append(supplement.to_dict())

        with open('supplements.json', 'w') as fp:
            json.dump(data_list, fp, indent=2)
