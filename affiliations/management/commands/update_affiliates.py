from tqdm import tqdm

from shopified_core.management import DropifiedBaseCommand
from affiliations.utils import LeadDynoAffiliations
from affiliations.models import LeadDynoSync


class Command(DropifiedBaseCommand):
    help = 'Store existing orders in elastic search'

    total_order_fetch = 0  # Number of imported orders since command start

    def add_arguments(self, parser):
        parser.add_argument('--noprogress', dest='progress',
                            action='store_false', help='Hide Progress')

    def start_command(self, *args, **options):
        self.progress = options['progress']

        affiliations = LeadDynoAffiliations()
        total_count = affiliations.count_remaining_visitors()
        total_count += affiliations.count_remaining_leads()
        total_count += affiliations.count_remaining_purchases()

        if self.progress and total_count > 0:
            self.obar = tqdm(total=total_count)

        affiliations.current_sync = LeadDynoSync.objects.create()
        for visitor in affiliations.fetch_remaining_visitors(as_generator=True):
            if self.progress:
                self.obar.update(1)

        for lead in affiliations.fetch_remaining_leads(as_generator=True):
            if self.progress:
                self.obar.update(1)

        for purchase in affiliations.fetch_remaining_purchases(as_generator=True):
            if self.progress:
                self.obar.update(1)

        affiliations.finish_sync()

        if self.progress and total_count > 0:
            self.obar.close()
