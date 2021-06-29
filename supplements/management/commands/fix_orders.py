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
    help = 'Fix order price'

    def start_command(self, *args, **options):
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
                order_sale_price = order.sale_price / 100

                line = order.order_items.first()
                store_sale_price = get_store_order_price(line)

                if store_sale_price == order_sale_price:
                    # order is correct; skipping
                    continue

                cost_paid = 0
                for line in order.order_items.all():
                    cost_paid += (line.amount * line.quantity) / 100

                for line in order.order_items.all():
                    sale_price = store_sale_price * line.amount / cost_paid
                    line.sale_price = sale_price
                    line.save()

                order.sale_price = store_sale_price * 100
                order.save()
                print(f"Fixed Order # {order.pk}")
            except:
                capture_exception()
