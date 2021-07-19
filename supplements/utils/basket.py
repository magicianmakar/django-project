import json
from supplements.models import BasketOrder
from my_basket.models import BasketOrderTrack
from decimal import Decimal


# virtual object for compabality with othert store types
class BasketStoreObj:
    def __init__(self):
        self.id = 0

    def get(self, id=False):
        return self

    def get_order(self, basket_order_id):
        basket_order = BasketOrder.objects.get(id=basket_order_id)
        order_data = basket_order.get_order_data()
        order_data['order_number'] = basket_order.id
        return order_data


class BasketStore:
    def __init__(self):
        self.store_type = 'mybasket'
        self.id = 0

    def create_order(self, user, order_data):

        basket_order = BasketOrder()
        basket_order.user = user
        basket_order.set_order_data(self.generate_order_metadata(order_data))
        basket_order.save()

        return basket_order

    def create_order_tracks(self, pls_order, basket_order):

        for order_item in pls_order.order_items.all():
            basket_order_track = BasketOrderTrack()
            basket_order_track.order_id = order_item.store_order_id
            basket_order_track.line_id = order_item.line_id
            basket_order_track.product_id = order_item.label.user_supplement.id
            basket_order_track.source_id = basket_order.id
            basket_order_track.basket_order_status = 'processing'
            basket_order_track.auto_fulfilled = True
            basket_order_track.store_id = self.id
            basket_order_track.user_id = pls_order.user_id
            basket_order_track.source_type = 'supplements'

            total_price = Decimal(pls_order.amount) / Decimal(100)
            shipping_price = Decimal(pls_order.shipping_price) / Decimal(100)
            products_price = total_price - shipping_price
            track_currency = "USD"

            order_data = {'aliexpress': {"end_reason": False}}
            order_data['aliexpress']['order_details'] = {
                "cost": {
                    'products': str(products_price.quantize(Decimal('0.01'))),
                    'shipping': str(shipping_price.quantize(Decimal('0.01'))),
                    'total': str(total_price.quantize(Decimal('0.01'))),
                    'currency': track_currency,
                }
            }

            basket_order_track.data = json.dumps(order_data)
            basket_order_track.save()
            order_item.order_track_id = basket_order_track.id
            order_item.save()

    def generate_order_metadata(self, order_data):
        order_metadata = {}
        order_metadata['billing_address'] = {
            'name': '{} {}'.format(order_data['billing_first_name'], order_data['billing_last_name']),
            'first_name': order_data['billing_first_name'],
            'last_name': order_data['billing_last_name'],
            'company': order_data['billing_company_name'],
            'address1': order_data['billing_address_line1'],
            'address2': order_data['billing_address_line2'],
            'city': order_data['billing_city'],
            'province': order_data['billing_state_code'],
            'zip': order_data['billing_zip_code'],
            'country': order_data['billing_country'],
            'country_code': order_data['billing_country_code'],
            'email': order_data['billing_email'],
            'phone': order_data['billing_phone'],
        }
        order_metadata['shipping_address'] = {
            'name': '{} {}'.format(order_data['shipping_first_name'], order_data['shipping_last_name']),
            'first_name': order_data['shipping_first_name'],
            'last_name': order_data['shipping_last_name'],
            'company': order_data['shipping_company_name'],
            'address1': order_data['shipping_address_line1'],
            'address2': order_data['shipping_address_line2'],
            'city': order_data['shipping_city'],
            'province': order_data['shipping_state_code'],
            'zip': order_data['shipping_zip_code'],
            'country': order_data['shipping_country'],
            'country_code': order_data['shipping_country_code'],
            'email': order_data['shipping_email'],
            'phone': order_data['shipping_phone'],
        }
        order_metadata['line_items'] = []
        for line_item in order_data['line_items']:
            line_item_filtered = {
                'id': line_item['id'],
                'quantity': line_item['quantity'],
                'price': line_item['price'],
                'title': line_item['title'],
                'sku': line_item['sku'],
            }
            order_metadata['line_items'].append(line_item_filtered)

        return order_metadata

    # static propery emulation
    objects = BasketStoreObj()
