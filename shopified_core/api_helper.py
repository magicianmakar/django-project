
class ApiHelperBase:

    def smart_board_sync(self, user, board):
        """
        Add Products to `board` if the config match
        Args:
            user: Parent user
            board: board to add products to

        Raises:
            NotImplementedError: if not not impmented in subsclass
                                 Only implmented in: N/A
        """
        raise NotImplementedError('Smart Board Sync')

    def after_delete_product_connect(self, product, source_id):
        raise NotImplementedError('After Delete Product Connect')

    def format_order_key(self, order_key):
        """
        Returns order key and store id
        Args:
            order_key: Order Key
        """
        raise NotImplementedError('Format Order Key')

    def get_user_stores_for_type(self, user, **kwargs):
        raise NotImplementedError('Get User Stores for Type')

    def get_unfulfilled_order_tracks(self, order_tracks):
        return order_tracks.filter(source_tracking='').exclude(source_status='FINISH')

    def create_image_zip(self, images, product):
        raise NotImplementedError('Create Image Zip')

    def set_order_note(self, store, order_id, note):
        raise NotImplementedError('Set Order Note')

    def get_product_path(self, pk):
        """
        Returns a path for product detail view
        Args:
            pk: Product ID
        """
        raise NotImplementedError('Get Product Path')

    def after_post_product_connect(self, product, source_id):
        raise NotImplementedError('After Post Product Connect')

    def get_connected_products(self, product_model, store, source_id):
        return product_model.objects.filter(
            store=store,
            source_id=source_id
        )

    def duplicate_product(self, product):
        """
        Returns duplicated product: utils.duplicate_product(product)
        Args:
            product: Product
        """
        raise NotImplementedError('Duplicate Product')

    def split_product(self, product, split_factor, user):
        """
        Returns splitted product ids: utils.split_product(product, split_factor)
        """
        raise NotImplementedError('Split Product')

    def product_save(self, data, user_id, target, request):
        """
        Save the product as non-connected product
        Currently not inplemented in Shopify
        """
        raise NotImplementedError('Product Save')

    def set_product_default_supplier(self, product, supplier):
        raise NotImplementedError('Set Product Default Supplier')

    def filter_productchange_by_store(self, store):
        pass

    def get_store_tracking_carriers(self, store):
        return []
