from django.core.paginator import Paginator


class SimplePaginator(Paginator):
    current_page = 0

    def page(self, number):
        self.current_page = number
        return super(SimplePaginator, self).page(number)

    def page_range(self):
        """
        Returns a 1-based range of pages for iterating through within
        a template for loop.
        """
        page_count = self.num_pages

        pages = range(max(1, self.current_page - 5), self.current_page) + \
            range(self.current_page, min(page_count + 1, self.current_page + 5))

        if 1 not in pages:
            pages = [1, None] + pages

        if page_count not in pages:
            pages = pages + [None, page_count]

        return pages


class FakePaginator(SimplePaginator):
    def set_current_page(self, page):
        self.current_page = page

    def page(self, number):
        """
        Returns a Page object for the given 1-based page number.
        """

        self.current_page = number

        number = self.validate_number(number)
        bottom = (number - 1) * self.per_page
        top = bottom + self.per_page
        if top + self.orphans >= self.count:
            top = self.count

        return self._get_page(self.orders, number, self)

    def set_orders(self, orders):
        self.orders = orders
