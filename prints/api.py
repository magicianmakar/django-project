import json

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ObjectDoesNotExist
from django.views.generic import View

from lib.exceptions import capture_exception

from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin

from . import tasks
from . import utils
from .models import CustomProduct, Order, OrderItem


class PrintsApi(ApiResponseMixin, View):
    store_type = None
    store_model = None
    product_model = None

    def dispatch(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode())
        except:
            data = {}
        self.store_type = request.GET.get('store_type') or request.POST.get('store_type') or data.get('store_type')
        self.store_model = utils.get_store_model(self.store_type)
        self.product_model = utils.get_product_model(self.store_type)
        self.track_model = utils.get_track_model(self.store_type)

        return super(PrintsApi, self).dispatch(request, *args, **kwargs)

    def delete_custom_product(self, request, user, data):
        try:
            custom_product_id = data.get('id')
            CustomProduct.objects.get(
                id=custom_product_id,
                user=user.models_user
            ).delete()

        except CustomProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        return self.api_success()

    def post_mockup(self, request, user, data):
        try:
            store = self.store_model.objects.get(id=data.get('store'))
            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        user = request.user.models_user
        variant_id = request.POST.get('variant_id')
        paired = request.POST.get('paired', 'true') == 'true'
        sku = request.POST.get('sku')

        left_img = request.POST.get('left_img')
        right_img = request.POST.get('right_img')
        img = request.POST.get('img')

        uploaded_images = [img]
        if paired:
            uploaded_images = []
            # 2 images are needed for mockup, duplicate one of them
            uploaded_images.append(left_img or right_img)
            uploaded_images.append(right_img or left_img)

        tasks.generate_mockup.apply_async(
            args=[self.store_type, data.get('store'),
                  sku, variant_id, uploaded_images,
                  paired],
            countdown=0,
            expires=120
        )

        return self.api_success({
            'status': 'ok',
            'pusher': {
                'key': settings.PUSHER_KEY,
                'channel': store.pusher_channel()
            }
        })

    def post_placed_item(self, request, user, data):
        data = json.loads(request.body.decode())

        try:
            store = self.store_model.objects.get(id=int(data['store']))
            store_content_type = ContentType.objects.get_for_model(store)

            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

            permissions.user_can_view(user, store)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        try:
            custom_product = CustomProduct.objects.get(
                pk=data.get('source_id'),
                user=user.models_user
            )
        except CustomProduct.DoesNotExist:
            return self.api_error('Product not found', status=404)

        order_item = OrderItem.objects.filter(
            order__content_type=store_content_type,
            order__object_id=store.id,
            order_data_id=data.get('order_data_id'),
        )
        if order_item.exists():
            order_name = order_item.first().order.order_name
            return self.api_error(f'Item already placed under {order_name}', status=302)

        try:
            variants_data = custom_product.get_variants_for_order(data.get('variant', []))
            prices = custom_product.product.get_price_by_sku(variants_data['custom']['shipment'])
        except Exception as e:
            return self.api_error(str(e), status=500)

        return self.api_success({
            'price': prices.get('dropified'),
            'from': variants_data['custom']['from']
        })

    @transaction.atomic
    def post_place_order(self, request, user, data):
        data = json.loads(request.body.decode())

        try:
            first_order_item = data['orders'][0]
            store = self.store_model.objects.get(id=int(first_order_item['store']))
            store_content_type = ContentType.objects.get_for_model(store)

            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

            permissions.user_can_view(user, store)

        except KeyError:
            return self.api_error('Order not found', status=500)

        except ObjectDoesNotExist:
            return self.api_error('Store not found', status=404)

        shipping_address = first_order_item.get('shipping_address')
        print_order, created = Order.objects.get_or_create(
            content_type=store_content_type,
            object_id=store.id,
            order_reference=first_order_item['print_order_info']['order_name'],
            user=user.models_user,
            defaults=dict(
                order_id=first_order_item['order_id'],
                customer_name=shipping_address.get('name', ''),
                customer_phone=shipping_address.get('phone') or '',
                address1=shipping_address.get('address1'),
                address2=shipping_address.get('address2') or '',
                city=shipping_address.get('city'),
                zip_code=shipping_address.get('zip'),
                province=shipping_address.get('province') or '',
                country_code=shipping_address.get('country_code'),
            )
        )
        if not created:
            return self.api_error('Order already placed', status=500)

        orders_result = []
        has_errors = False
        fulfilled_order = None

        for order in data.get('orders', []):
            order_result = order.get('print_order_info', {})
            order_result['order_data'] = order.get('id')
            order_result['order_status'] = ''

            try:
                custom_product = CustomProduct.objects.get(
                    pk=order.get('source_id'),
                    user=user.models_user
                )

                line_item = custom_product.get_order_item(order)

            except CustomProduct.DoesNotExist:
                has_errors = True
                order_result['error'] = 'Saved Product not found'
                orders_result.append(order_result)
                continue

            except Exception as e:
                has_errors = True
                order_result['error'] = str(e)
                orders_result.append(order_result)
                continue

            line_item['order'] = print_order
            OrderItem.objects.create(**line_item)
            order_result['order_status'] = ''
            orders_result.append(order_result)

        if has_errors:
            transaction.set_rollback(True)
        else:
            print_order.refresh_from_db()

            try:
                print_order.place_stripe_order(user.models_user)
            except Exception as e:
                transaction.set_rollback(True)
                return self.api_error(str(e), status=500)

            fulfilled_order = utils.place_order(print_order)
            for order_result in orders_result:
                order_result['success'] = True
                order_result['order_status'] = 'Marked as Ordered'

        return self.api_success({
            'orders': orders_result,
            'fulfilled_order': fulfilled_order
        })

    def post_sync_order(self, request, user, data):
        order_name = data.get('source_id')

        try:
            order = Order.objects.get(order_name=order_name,)
        except Order.DoesNotExist:
            return self.api_error('Order not found', status=404)

        try:
            store = order.store_object
            if not user.can('place_orders.sub', store):
                raise PermissionDenied()

            permissions.user_can_view(user, store)
        except:
            return self.api_error('Permission denied', status=403)

        if data.get('connect'):
            for item in order.line_items.all():
                try:
                    track = self.track_model.objects.get(
                        store=store,
                        order_id=order.order_id,
                        line_id=item.line_id,
                        source_id=order.order_name,
                        source_type='dropified-print'
                    )
                    track_content_type = ContentType.objects.get_for_model(track)

                except ObjectDoesNotExist:
                    capture_exception(level='warning')
                    continue

                item.track_content_type = track_content_type
                item.track_object_id = track.id
                item.save()

        return self.api_success({'details': utils.get_tracking_details(order)})
