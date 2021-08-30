import re
from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.utils.functional import cached_property
from elasticsearch_dsl import Search

from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from munch import Munch

from product_core.utils import get_product_from_hit
from product_core.models import ProductBoard
from shopified_core.paginators import FakePaginator
from shopified_core.utils import safe_str
from shopify_orders.utils import get_elastic


class BaseTemplateView(TemplateView):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: dict) -> dict:
        return super().get_context_data(**kwargs)


class ProductsListView(BaseTemplateView):
    template_name = 'products/list.html'
    result_per_page = 24

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx.update(self.get_products())

        ctx['boards'] = ProductBoard.objects.filter(user=self.request.user.models_user)
        return ctx

    def get_products(self):
        es = get_elastic()
        s = Search(using=es, index="products-index") \
            .filter("term", user=self.request.user.id)

        if self.filters.title:
            s = s.query("match", title=self.filters.title)

        if self.filters.store:
            s = s.filter("term", store=self.filters.store)

        if self.filters.board:
            s = s.filter("term", boards=self.filters.board)

        if self.filters.platform:
            s = s.filter("term", platform=self.filters.platform)

        if self.filters.tags:
            s = s.filter("term", tags=self.filters.tags)

        if self.filters.status == 'c':
            s = s.filter("range", source_id={'gt': 0})
        elif self.filters.status == 'n':
            s = s.exclude("range", source_id={'gt': 0})

        s = s.sort('_score', self.sort_field)

        page_num = int(self.request.GET.get('page', 1))
        starts = (page_num - 1) * self.result_per_page
        ends = page_num * self.result_per_page

        response = s[starts:ends].execute()

        products = self.products_from_hit(response)

        paginator = FakePaginator(range(0, response.hits.total), 24)
        paginator.set_orders(products)
        current_page = paginator.page(page_num)

        return {
            'products': products,
            'paginator': paginator,
            'current_page': current_page,
        }

    def products_from_hit(self, hits):
        products = []
        board_ids = defaultdict(list)

        for hit in hits:
            product = get_product_from_hit(hit)
            products.append(product)
            if product.boards_list:
                for board_id in product.boards_list:
                    board_ids[board_id].append(product)

        for board in ProductBoard.objects.filter(user=self.request.user.models_user, id__in=board_ids.keys()):
            for product in board_ids[board.id]:
                product.board = board

        return products

    @cached_property
    def filters(self):
        return Munch({
            'status': safe_str(self.request.GET.get('status')).strip(),
            'store': safe_str(self.request.GET.get('store')).strip(),
            'platform': safe_str(self.request.GET.get('platform')).strip(),
            'title': safe_str(self.request.GET.get('title')).strip(),
            'tags': safe_str(self.request.GET.get('tags')).strip(),
            'board': safe_str(self.request.GET.get('board')).strip(),
        })

    @cached_property
    def sort_field(self):
        field = self.request.GET.get('sort')
        if field and re.sub(r'^-', '', field) in ['created_at', 'updated_at', 'price']:
            return field
        else:
            return '-created_at'
