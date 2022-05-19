import json

from django.http import JsonResponse

from lib.exceptions import capture_message
from shopified_core import permissions
from shopified_core.api_base import ApiBase

from .api_helper import FBMarketplaceApiHelper
from .models import FBMarketplaceBoard, FBMarketplaceOrderTrack, FBMarketplaceProduct, FBMarketplaceStore


class FBMarketplaceStoreApi(ApiBase):
    store_label = 'FBMarketplace'
    store_slug = 'fb_marketplace'
    board_model = FBMarketplaceBoard
    product_model = FBMarketplaceProduct
    order_track_model = FBMarketplaceOrderTrack
    store_model = FBMarketplaceStore
    helper = FBMarketplaceApiHelper()

    def post_store_add(self, request, user, data):
        if user.is_subuser:
            return self.api_error('Sub-Users can not add new stores.', status=401)

        can_add, total_allowed, user_count = permissions.can_add_store(user)

        if not can_add:
            if user.profile.plan.is_free and user.can_trial() and not user.profile.from_shopify_app_store():
                from shopify_oauth.views import subscribe_user_to_default_plan

                subscribe_user_to_default_plan(user)
            else:
                capture_message(
                    'Add Extra Facebook Marketplace Store',
                    level='warning',
                    extra={
                        'user': user.email,
                        'plan': user.profile.plan.title,
                        'stores': user.profile.get_fb_marketplace_stores().count()
                    }
                )

                if user.profile.plan.is_free and not user_count:
                    return self.api_error('Please Activate your account first by visiting:\n{}'.format(
                        request.build_absolute_uri('/user/profile#plan')), status=401)
                else:
                    return self.api_error('Your plan does not support connecting another Facebook Marketplace store. '
                                          'Please contact support@shopifiedapp.com to learn how to connect more stores.')

        title = data.get('title', '').strip()

        if len(title) > FBMarketplaceStore._meta.get_field('title').max_length:
            return self.api_error('The title is too long.', status=400)

        try:
            store = FBMarketplaceStore.objects.filter(
                user=user.models_user,
                title=title,
            ).latest('-pk')
        except FBMarketplaceStore.DoesNotExist:
            store = FBMarketplaceStore(
                user=user.models_user,
                title=title,
            )

        permissions.user_can_add(user, store)

        store.is_active = True
        store.save()

        return self.api_success({'status': 'ok'})

    def get_product(self, request, user, data):
        try:
            product = FBMarketplaceProduct.objects.get(id=data.get('product_id'))
            permissions.user_can_view(user, product)
            data = json.loads(product.data)
            data['id'] = product.id

        except FBMarketplaceProduct.DoesNotExist:
            return self.api_error('Product not found')

        return JsonResponse({'product': data}, safe=False)
