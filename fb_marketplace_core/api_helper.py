from django.urls import reverse

from shopified_core.api_helper import ApiHelperBase

from . import tasks, utils


class FBMarketplaceApiHelper(ApiHelperBase):
    def smart_board_sync(self, user, board):
        pass

    def product_save(self, data, user_id, target, request):
        return tasks.product_save(data, user_id)

    def duplicate_product(self, product):
        return utils.duplicate_product(product)

    def get_product_path(self, pk):
        return reverse('fb_marketplace:product_detail', args=[pk])

    def after_post_product_connect(self, product, source_id):
        product.sync()
