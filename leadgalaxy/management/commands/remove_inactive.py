import arrow
import traceback
from collections import defaultdict

from django.db.models import Count

from tqdm import tqdm

from last_seen.models import LastSeen
from leadgalaxy.models import ShopifyProduct, ShopifyStore, ShopifyOrderTrack, GroupPlan
from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import using_replica
from shopify_orders.models import ShopifyOrder, ShopifySyncStatus, ShopifyOrderLog
from shopify_orders.utils import get_elastic
from profit_dashboard.models import AliexpressFulfillmentCost


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Remove data from the database, otherwise report numbers')
        parser.add_argument('--paid', action='store_true', help='Remove inactive stores on paid plans')
        parser.add_argument('--no-gdpr', dest='gdpr', action='store_false', help='Remove stores without GDPR remove request')
        parser.add_argument('--new-first', action='store_true', help='Start with new stores first')
        parser.add_argument('--least-orders', action='store_true', help='Start with new stores first')
        parser.add_argument('--no-progress', dest='progress', action='store_false', help='Show progress')
        parser.add_argument('--no-uninstall', action='store_true', help='Show progress')
        parser.add_argument('--not-found', action='store_true', help='Delete stores with not found errors')

    def start_command(self, *args, **options):
        self.active_stores = [i.shop for i in ShopifyStore.objects.filter(is_active=True).only('shop')]

        stores = ShopifyStore.objects.filter(is_active=False)

        if not options['paid']:
            plan_ids = list(GroupPlan.objects.filter(title__in=[
                'Shopify Free Plan',
                'Free Stripe Plan',
                'Free Plan',
                'Starter',
                'Startup',
            ]).values_list('id', flat=True))

            stores = stores.filter(user__profile__plan_id__in=plan_ids)

        if options['gdpr']:
            stores = stores.exclude(delete_request_at=None)

        if options['not_found']:
            stores = stores.filter(uninstall_reason='HTTP:404')

        if not options['no_uninstall']:
            stores = stores.exclude(uninstalled_at__isnull=True).filter(uninstalled_at__lt=arrow.utcnow().replace(days=-30).datetime)

        stores = stores.select_related('user', 'user__profile', 'user__profile__plan')

        if options['least_orders']:
            stores = stores.order_by('shopifysyncstatus__orders_count')
        else:
            stores = stores.order_by('-uninstalled_at' if options['new_first'] else 'uninstalled_at')

        if not stores.exists():
            self.write('Nothing to delete')
            return

        if options['progress']:
            self.progress_total(stores.count())

        self.plan_count = defaultdict(int)
        self.ignored_plan_count = defaultdict(int)
        self.deleted_models = defaultdict(int)
        self.stores_to_delete = []

        self.load_stores(stores)

        self.progress_close()

        if options['force']:
            if options['progress']:
                self.progress_total(len(self.stores_to_delete))

            # random.shuffle(self.stores_to_delete)
            self.delete_stores()

        self.write(f'Stores to delete: {len(self.stores_to_delete)}')
        self.write('Plans Count:')
        for k, v in self.plan_count.items():
            self.write(f'\t{v:3,}\t{k}')

        self.write('Ignored Plans Count:')
        for k, v in self.ignored_plan_count.items():
            self.write(f'\t{v:3,}\t{k}')

        self.write('Deleted Models Count:')
        for k, v in self.deleted_models.items():
            self.write(f'\t{v:3,}\t{k}')

    def load_stores(self, stores):
        for store in stores:
            self.progress_update()
            ignore = False

            try:
                when_seen = LastSeen.objects.when(store.user, 'website')
                seen = arrow.get(when_seen).humanize()
                last_30_days = arrow.get(when_seen) > arrow.utcnow().replace(days=-30)
            except KeyboardInterrupt:
                raise
            except:
                seen = None
                last_30_days = False

            if store.shop in self.active_stores:
                self.ignored_plan_count[':ignored'] += 1
                ignore = True

            if last_30_days:
                self.ignored_plan_count[':last_30_days'] += 1
                ignore = True

            plan = store.user.profile.plan

            if False:
                self.write(f'{store.shop.ljust(50)} | {plan.title.ljust(50)} | {plan.monthly_price} | {seen} | {last_30_days} | Ignore: {ignore}')

            if ignore:
                self.ignored_plan_count[plan.title] += 1
            else:
                self.plan_count[plan.title] += 1
                self.stores_to_delete.append(store)

    def load_orders_count(self, stores_filter):
        self.write(f'Load orders count for {len(self.stores_to_delete)} stores')

        self.stores_orders_count = {}
        stores = using_replica(ShopifyStore, False).filter(is_active=False) \
                                                   .annotate(orders=Count('shopifyorder')).values('id', 'shop', 'orders')

        for store in stores:
            self.stores_orders_count[store['id']] = store['orders']
            self.stores_orders_count[store['shop']] = store['orders']

        for store in self.stores_to_delete:
            store.orders = self.stores_orders_count.get(store.id)

        self.stores_to_delete = sorted(self.stores_to_delete, key=lambda a: a.orders)

    def delete_stores(self):
        for store in self.stores_to_delete:
            self.progress_update()
            try:
                self.delete_shopify_store(store)
            except KeyboardInterrupt:
                raise
            except:
                traceback.print_exc()

    def delete_shopify_store(self, store):
        self.set_description(shop=store.shop)

        match = {
            'store': store
        }

        try:
            es = ShopifySyncStatus.objects.filter(store=store).elastic
        except:
            es = False

        # orders_count = ShopifyOrder.objects.filter(**match).count()
        # if orders_count > 3000:
        #    self.write(f'>>> SKIP: {store.shop} {orders_count} ShopifyOrder')
        #    return

        orderlines = 0
        # orderlines = self.delete_model_from_db(ShopifyOrderLine, {'order__store': store}, store)
        # if orderlines is None:
        #     return

        orders = self.delete_model_from_db(ShopifyOrder, match, store)
        if orders is None:
            return

        products = self.delete_model_from_db(ShopifyProduct, match, store)
        if products is None:
            return

        costs = self.delete_model_from_db(AliexpressFulfillmentCost, match, store)
        logs = self.delete_model_from_db(ShopifyOrderLog, match, store)
        tracks = self.delete_model_from_db(ShopifyOrderTrack, match, store)

        if orders is None or products is None or tracks is None:
            return

        if es:
            self.delete_store_orders_es(store, es=es)

        self.deleted_models['orderlines'] += orderlines
        self.deleted_models['orders'] += orders
        self.deleted_models['products'] += products
        self.deleted_models['tracks'] += tracks

        uninstall = arrow.get(store.uninstalled_at).humanize() if store.uninstalled_at else 'N/A'
        self.write('|'.join([
            store.shop.ljust(50),
            f'Uninstall: {uninstall.ljust(20)}',
            f'Orders {orders:3,}',
            f'Lines {orderlines:3,}',
            f'Products {products:3,}',
            f'Tracks {tracks:3,}',
            f'Costs {costs:3,}',
            f'Logs {logs:3,}'
        ]))

        self.set_description(shop=store.shop, model_name='Delete Store')
        store.delete()
    #

    def delete_model_from_db(self, model, match, store, steps=5000):
        name = str(model).split('.').pop().strip("'>")
        self.set_description(shop=store.shop, model_name=name)

        model_ids = list(using_replica(model).filter(**match).values_list('id', flat=True))
        model_count = len(model_ids)

        self.set_description(shop=store.shop, model_name=name, model_count=model_count)

        # if model_count > 30000:
        #     self.write(f'>>> SKIP: {name} {model_count:3,}')
        #     return None
        # return model_ids.delete()[0]

        if model_count > steps:
            obar = tqdm(total=model_count, smoothing=0)
            obar.set_description(f' {name} {store.shop}')
        else:
            obar = None

        start = 0
        count = 0
        while start < model_count:
            order_ids = model_ids[start:start + steps]
            model.objects.filter(id__in=order_ids).delete()

            start += steps
            count += len(order_ids)

            if obar:
                obar.update(len(order_ids))

        if obar:
            obar.close()

        return count

    def delete_store_orders_es(self, store, es=None):
        deleted = []

        if es:
            es = get_elastic()
            if es:
                body = {
                    'query': {
                        'bool': {
                            'must': [
                                {'term': {'store': store.id}},
                            ],
                        },
                    },
                }

                r = es.delete_by_query(index='shopify-order', doc_type='order', body=body)
                deleted.append(r['total'])

                ShopifySyncStatus.objects.filter(store=store, elastic=True).update(elastic=False)

        return deleted

    def set_description(self, shop=None, model_name=None, model_count=None):
        if self.progress_bar:
            info = []
            if shop:
                info.append(f'[{shop}]')

            if model_name:
                if model_count is None:
                    info.append(f"[{model_name}]")
                else:
                    info.append(f"[{model_name} {model_count:3,}]")

            info.extend([
                f"(Lines {self.deleted_models['orderlines']:3,})",
                f"(Orders {self.deleted_models['orders']:3,})",
                f"(Products {self.deleted_models['products']:3,})",
                f"(Tracks {self.deleted_models['tracks']:3,})",
            ])

            self.progress_bar.set_description(' '.join(info))
