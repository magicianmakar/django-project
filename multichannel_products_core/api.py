import json
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from rest_framework.exceptions import PermissionDenied

from django.contrib import messages

from bigcommerce_core.master_product_helper import BigCommerceMasterProductHelper
from commercehq_core.master_product_helper import CommerceHQMasterProductHelper
from ebay_core.master_product_helper import EbayMasterProductHelper
from facebook_core.master_product_helper import FBMasterProductHelper
from gearbubble_core.master_product_helper import GearBubbleMasterProductHelper
from google_core.master_product_helper import GoogleMasterProductHelper
from groovekart_core.master_product_helper import GrooveKartMasterProductHelper
from infinite_pagination.paginator import InfinitePaginator
from leadgalaxy.master_product_helper import ShopifyMasterProductHelper
from multichannel_products_core import tasks
from multichannel_products_core.models import MasterProduct, ProductTemplate
from multichannel_products_core.utils import get_store_child, get_child_link
from profits.utils import get_stores
from shopified_core import permissions
from shopified_core.mixins import ApiResponseMixin
from shopified_core.utils import app_link, safe_int
from woocommerce_core.master_product_helper import WooMasterProductHelper


def get_helper_class(store_type: str, product_id=None):
    """
    Get helper class for child with passed store type and product id

    :param store_type:
    :type store_type: str
    :param product_id:
    :type product_id:
    """
    if store_type == 'fb':
        return FBMasterProductHelper(product_id=product_id)
    if store_type == 'ebay':
        return EbayMasterProductHelper(product_id=product_id)
    if store_type == 'shopify':
        return ShopifyMasterProductHelper(product_id=product_id)
    if store_type == 'woo':
        return WooMasterProductHelper(product_id=product_id)
    if store_type == 'chq':
        return CommerceHQMasterProductHelper(product_id=product_id)
    if store_type == 'bigcommerce':
        return BigCommerceMasterProductHelper(product_id=product_id)
    if store_type == 'gear':
        return GearBubbleMasterProductHelper(product_id=product_id)
    if store_type == 'gkart':
        return GrooveKartMasterProductHelper(product_id=product_id)
    if store_type == 'google':
        return GoogleMasterProductHelper(product_id=product_id)


class MasterProductApi(ApiResponseMixin):

    def post_child_product(self, request, user, data):
        """
        Create child product from parent
        """
        parent_product_id = data.get('parent_product')
        if not parent_product_id:
            return self.api_error('Parent Product ID is missing', status=422)

        try:
            parent = MasterProduct.objects.get(id=parent_product_id)
            permissions.user_can_edit(user, parent)
        except MasterProduct.DoesNotExist:
            return self.api_error('Parent Product not found', status=404)

        store_id = data.get('store', {}).get('id')
        if not store_id:
            return self.api_error('Store ID is missing', status=422)
        store_type = data.get('store', {}).get('type')
        if not store_type:
            return self.api_error('Store Type is missing', status=422)

        override_fields = data.get('override_fields', {})
        publish = data.get('publish', False)

        can_add, total_allowed, user_count = permissions.can_add_product(user.models_user)
        if not can_add:
            return self.api_error(
                f'Your current plan allows up to {total_allowed} saved product(s). Currently you '
                f'have {user_count} saved products.', status=401)

        helper = get_helper_class(store_type)
        result = helper.create_new_product(user, store_id, parent, override_fields, publish=publish)

        if publish and store_type in ['fb', 'ebay', 'google']:
            messages.info(request,
                          '<div style="display: flex; align-items: center;">'
                          '<i class="fa fa-info-circle" style="font-size: 24px;margin-right: 1rem;"></i>'
                          'Additional fields are required to list this product to the store.'
                          'Please fill out required fields and try exporting the product again.'
                          '</div>',
                          extra_tags='sd_product_details')
        return self.api_success(result)

    def post_parent_product(self, request, user, data):
        """
        Create parent from child product or extension or save parent product with passed children
        """
        store_type = data.get('store_type')
        if data.get('store_type'):
            product_id = data.get('product_id')
            helper = get_helper_class(store_type, product_id)

            if not helper.is_master_product_connected():
                mapped_data = dict(data=json.dumps(helper.get_product_mapped_data()))
                result = tasks.product_save(mapped_data, user.id, is_extension=False)

                if result.get('product'):
                    parent = MasterProduct.objects.get(id=result.get('product').get('id'))
                    helper.connect_parent_product(parent)
            else:
                result = {}

            messages.info(request,
                          '<div style="display: flex; align-items: center;">'
                          '<i class="fa fa-info-circle" style="font-size: 24px;margin-right: 1rem;"></i>'
                          'Now you can connect this product to other stores and platforms.'
                          '</div>',
                          extra_tags='product_details')

        elif data.get('product'):  # save
            result = tasks.product_save(data, user.id, is_extension=False)
            parent_id = result.get('product', {}).get('id') if isinstance(result, dict) else None
            if parent_id:
                parent = MasterProduct.objects.get(id=parent_id)
                children = data.get('children', [])
                for child in children:
                    helper = get_helper_class(child.get('type'), child.get('id'))
                    helper.update_product(user, parent)
        else:
            result = tasks.product_save(data, user.id)  # create from extension
        return self.api_success(result)

    def delete_product(self, request, user, data):
        """
        Delete parent product
        """
        try:
            pk = safe_int(data.get('product'))
            product = MasterProduct.objects.get(pk=pk)
            permissions.user_can_delete(user, product)

        except MasterProduct.DoesNotExist:
            return self.api_error('Product does not exist.', status=404)

        if not user.can('delete_products.sub'):
            raise PermissionDenied()

        product.delete()

        return self.api_success()

    def post_product_notes(self, request, user, data):
        """
        Save parent product notes
        """
        product = MasterProduct.objects.get(id=data.get('product'))
        permissions.user_can_edit(user, product)

        product.notes = data.get('notes')
        product.save()

        return self.api_success()

    def post_disconnect_parent_product(self, request, user, data):
        """
        Disconnect parent product from child
        """
        store_type = data.get('store_type')
        product_id = data.get('product')

        helper = get_helper_class(store_type, product_id)
        helper.check_user_permissions(user, 'edit')
        helper.connect_parent_product(None)

        return self.api_success()

    def get_find_product(self, request, user, data):
        """
        Find parent product
        """
        try:
            source_id = data.get('aliexpress')
            product = MasterProduct.objects.get(user=user.models_user, original_url__icontains=source_id)
            permissions.user_can_view(user, product)

            return self.api_success({'url': app_link(product.url)})
        except:
            return self.api_error('Product not found', status=404)

    def post_export_child_product(self, request, user, data):
        """
        Export child product
        """
        product_id = data.get('product')
        if not product_id:
            return self.api_error('Product ID is missing', status=422)

        store_type = data.get('store_type')
        if not store_type:
            return self.api_error('Store Type is missing', status=422)

        helper = get_helper_class(store_type, product_id)
        result = {'product': helper.send_product_to_store(user)}

        if store_type in ['fb', 'ebay', 'google']:
            messages.info(request,
                          '<div style="display: flex; align-items: center;">'
                          '<i class="fa fa-info-circle" style="font-size: 24px;margin-right: 1rem;"></i>'
                          'Additional fields are required to export this product. '
                          'Please fill all required fields and try again.'
                          '</div>',
                          extra_tags='sd_product_details')
        return self.api_success(result)

    def post_multichannel_products(self, request, user, data):
        """
        List parent products
        """
        page = safe_int(data.get('page'), 1)
        limit = 100

        products = MasterProduct.objects.filter(user=user.models_user)
        if data.get('query'):
            products = products.filter(title__icontains=data.get('query'))
        products = list(products.values('id', 'title', 'images'))

        paginator = InfinitePaginator(products, limit)
        products = paginator.page(page).object_list

        for product in products:
            images = json.loads(product['images'])
            product['image'] = {'src': images[0] if images else None}

        return self.api_success({
            'products': products,
            'page': page,
            'next': page + 1 if len(products) == limit else None})

    def post_link_product(self, request, user, data):
        """
        Link existing parent product to child product
        """
        try:
            store_type = data.get('store_type')
            product_id = data.get('product')
            master_id = data.get('master_id')

            product = MasterProduct.objects.get(id=master_id)
            permissions.user_can_edit(user, product)

            helper = get_helper_class(store_type, product_id)
            store_child = get_store_child(product, store_type, helper.product.store)
            if store_child:
                error_message = 'The selected multi-channel product already has a listing in this store.'
                link = get_child_link(store_child)
                if link:
                    error_message = f'{error_message}:\n' \
                                    f'<a href="{request.build_absolute_uri(link)}" target="_blank">' \
                                    f'{request.build_absolute_uri(link)}' \
                                    f'</a>'
                return self.api_error(error_message, status=400)
            helper.connect_parent_product(product)
            helper.update_master_variants_map(product)

            result = {'product': helper.update_product(user, product)}

            return self.api_success(result)
        except:
            return self.api_error('Product not found', status=404)

    def post_variants_mapping(self, request, user, data):
        """
        Update master to children variants mapping
        """
        try:
            master_product = data.get('master_product')
            child_data = data.get('child_data')

            product = MasterProduct.objects.get(id=master_product)
            permissions.user_can_edit(user, product)

            helper = get_helper_class(child_data.get('type'), child_data.get('product'))
            child = helper.product
            permissions.user_can_edit(user, child)

            child.set_master_variants_map(child_data.get('variants_map'))
            return self.api_success()
        except:
            return self.api_error('Product not found', status=404)

    def post_template_save(self, request, user, data):
        """
        Add or create product template
        """
        try:
            template_data = data.copy()

            template_id = template_data.pop('template_id', None)
            template_type = template_data.get('type')
            store_id = template_data.pop('store_id', None)
            store_type = template_data.pop('store_type', None)
            store = get_stores(user, store_type).get(id=store_id)

            if template_type == 'pricing':
                template_data['price_amount'] = Decimal(template_data['price_amount'])
                template_data['price_override_amount'] = Decimal(template_data['price_override_amount'])
                template_data['compare_price_amount'] = Decimal(template_data['compare_price_amount'])
                template_data['compare_price_override_amount'] = Decimal(template_data['compare_price_override_amount'])

            if template_id:
                ProductTemplate.objects.filter(id=template_id).update(**template_data)
                template = ProductTemplate.objects.get(id=template_id)
            else:
                template = ProductTemplate.objects.create(id=template_id, store=store, **template_data)

            if template and template.is_active:
                store_content_type = ContentType.objects.get_for_model(store)
                ProductTemplate.objects.exclude(id=template.id).filter(
                    object_id=store_id, content_type=store_content_type,
                    type=template.type, is_active=True).update(is_active=False)

            return self.api_success()
        except Exception as e:
            return self.api_error(str(e), status=400)

    def delete_template(self, request, user, data):
        try:
            pk = safe_int(data.get('template'))
            product = ProductTemplate.objects.get(pk=pk)

        except ProductTemplate.DoesNotExist:
            return self.api_error('Template does not exists', status=404)

        product.delete()

        return self.api_success()
