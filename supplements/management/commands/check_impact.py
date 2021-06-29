import simplejson as json

from django.contrib.auth.models import User
from django.db.models import Q

from leadgalaxy.models import ShopifyProduct
from lib.exceptions import capture_exception
from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import get_store_api
from supplements.models import PLSOrderLine


def get_store_order_price(line):
    store_type = line.store_type
    order_id = line.store_order_id
    store_id = line.store_id
    line_id = line.line_id
    StoreApi = get_store_api(store_type)

    user = User.objects.filter(is_superuser=True).get()

    store_order_id = f'{store_id}_{order_id}_{line_id}'

    api_result = StoreApi.get_order_data(
        None,
        user,
        {'order': store_order_id, 'original': '1'},
    )

    order_data = json.loads(api_result.content.decode("utf-8"))
    return order_data['total']


class Command(DropifiedBaseCommand):
    help = 'Check impact'

    def start_command(self, *args, **options):
        impact = 0

        bundle_product = ShopifyProduct.objects.filter(~Q(bundle_map__isnull=True))
        for b_product in bundle_product:

            mapped_products = json.loads(b_product.bundle_map)
            products = list(mapped_products.values())[0]
            product_ids = [p['id'] for p in products]

            shopify_products = ShopifyProduct.objects.filter(
                id__in=product_ids,
            )

            user_supplement_ids = []
            for shopify_product in shopify_products:
                supplier = shopify_product.default_supplier
                if supplier.is_pls:
                    user_supplement_id = supplier.product_url.split('/')[-1]
                    user_supplement_ids.append(user_supplement_id)

            lines = PLSOrderLine.objects.filter(
                label__user_supplement_id__in=user_supplement_ids,
            ).first()
            order = lines.pls_order
            try:
                line = order.order_items.first()

                order_sale_price = order.sale_price / 100

                store_sale_price = get_store_order_price(line)

                if store_sale_price == order_sale_price:
                    # order is correct; skipping
                    continue
                print(f"Impact on Order # {order.pk}")
                impact += (order_sale_price - store_sale_price)
            except:
                capture_exception()

        print(f"Total impact: ${impact}")
