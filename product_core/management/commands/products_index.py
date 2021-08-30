from elasticsearch.exceptions import NotFoundError
from elasticsearch.helpers import streaming_bulk
from tqdm import tqdm

from leadgalaxy.models import GroupPlan
from product_core.utils import get_dataset
from shopified_core.commands import DropifiedBaseCommand
from shopified_core.models_utils import get_product_model
from shopify_orders.utils import get_elastic


class Command(DropifiedBaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--create', dest='create', action='store_true', help='Create Elasticsearch Index if it doesn\'t exist')
        parser.add_argument('--delete', dest='delete', action='store_true', help='Delete Elasticsearch Index')
        parser.add_argument('--user', dest='user', action='append', type=int, help='User Stores to index')
        parser.add_argument('--days', dest='days', action='store', type=int, help='Index order in the least number of days')
        parser.add_argument('--slug', dest='slug', action='store', default='research', type=str, help='Plan slug')
        parser.add_argument('--reset', dest='reset', action='store_true', help='Delete Store indexed orders before indexing')
        parser.add_argument('--dry-run', dest='dry_run', action='store_true', help='Show what will be indexed')
        parser.add_argument('--no-progress', dest='progress', action='store_false', help='Show stores indexing progress')

    def start_command(self, *args, **options):
        self.es = get_elastic()
        if options['delete']:
            self.write('Deleting index...')
            self.es.indices.delete(index='products-index')
            return

        if options['create']:
            self.write('Create index...')
            self.set_mappings()
            return

        plans = GroupPlan.objects.filter(slug__contains=options['slug'])
        self.write('Plans: {}'.format(", ".join([i.slug for i in plans])))
        for plan in plans:
            profiles = plan.userprofile_set.all()
            bar = tqdm(total=profiles.count() * 4, smoothing=0)
            for profile in profiles:
                self.index_model(profile.user, 'shopify', options, bar)
                self.index_model(profile.user, 'chq', options, bar)
                self.index_model(profile.user, 'woo', options, bar)
                self.index_model(profile.user, 'bigcommerce', options, bar)

                profile.index_products = True
                profile.save()

            bar.close()

    def index_model(self, user, platform, options, bar):
        bar.set_description(f'{user.email}')
        bar.update()

        products = get_product_model(platform).objects.filter(user=user)

        if options['progress']:
            self.progress_total(products.count())
            self.progress_description(f'Indexing {platform}')

        for ok, item in streaming_bulk(self.es, self.get_products_iterator(products, platform)):
            self.progress_update()

        self.progress_close()

    def get_products_iterator(self, products, platform):
        for product in products.iterator():
            yield get_dataset(product, platform)

    def set_mappings(self):
        try:
            self.es.indices.get(index='products-index')
            self.write('Index already exists')

        except NotFoundError:
            self.es.indices.create(index='products-index', body={
                "mappings": {
                    "product": {
                        "properties": {
                            "user": {"type": "keyword"},
                            "store": {"type": "keyword"},
                            "platform": {"type": "keyword"},

                            "source_id": {"type": "keyword"},

                            "title": {"type": "text", "analyzer": "english"},
                            "price": {"type": "float"},
                            "product_type": {"type": "keyword"},

                            "tags": {"type": "keyword"},
                            "boards": {"type": "keyword"},

                            "created_at": {"type": "date"},
                            "updated_at": {"type": "date"},
                        }
                    }
                }
            })
