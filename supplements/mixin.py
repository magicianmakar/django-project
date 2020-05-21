from django.shortcuts import reverse
from django.utils.html import format_html

from bs4 import BeautifulSoup

from supplements.lib.authorizenet import charge_customer_profile, get_customer_payment_profile


class PLSupplementMixin:
    is_admin_editable = True

    @property
    def thumbnail(self):
        return self.images.filter(position=0).get().image_url

    @property
    def description_short(self):
        description = BeautifulSoup(self.description, features="lxml")
        words = description.text.split()
        if len(words) > 8:
            return ' '.join(words[:8]) + '...'

        return description.text

    @property
    def shipping_groups_string(self):
        groups = [str(g) for g in self.shipping_countries.all()]
        return ", ".join(sorted(groups))

    def to_dict(self):
        image_urls = [i.image_url for i in self.images.all().order_by('position')]
        shipping_countries = self.shipping_countries.all()

        data = dict(
            title=self.title,
            cost_price=self.cost_price,
            description=self.description,
            tags=self.tags,
            category=self.category,
            wholesale_price=self.wholesale_price,
            label_template_url=self.label_template_url,
            image_urls=image_urls,
            shipstation_sku=self.shipstation_sku,
            shipping_countries=[c.to_dict() for c in shipping_countries]
        )
        return data

    def get_url(self):
        return reverse('pls:supplement', kwargs={'supplement_id': self.id})

    @property
    def is_approved(self):
        return False

    @property
    def is_awaiting_review(self):
        return False


class UserSupplementMixin(PLSupplementMixin):

    def to_dict(self):
        image_urls = [i.image_url for i in self.images.all().order_by('position')]

        data = dict(
            title=self.title,
            cost_price=self.cost_price,
            description=self.description,
            tags=self.tags,
            category=self.category,
            label_template_url=self.label_template_url,
            image_urls=image_urls,
            shipstation_sku=self.shipstation_sku,
            shipping_countries=self.pl_supplement.shipping_groups_string,
            price=self.price,
            compare_at_price=self.compare_at_price,
        )

        if self.current_label:
            data['label_url'] = self.current_label.url

        return data

    def get_url(self):
        return reverse('pls:user_supplement', kwargs={'supplement_id': self.id})

    @property
    def cost_price(self):
        return self.pl_supplement.cost_price

    @property
    def wholesale_price(self):
        return self.pl_supplement.wholesale_price

    @property
    def shipstation_sku(self):
        return self.pl_supplement.shipstation_sku

    @property
    def label_template_url(self):
        return self.pl_supplement.label_template_url

    @property
    def is_approved(self):
        if not self.current_label:
            return False

        return self.current_label.is_approved

    @property
    def is_awaiting_review(self):
        if not self.current_label:
            return False

        return self.current_label.is_awaiting_review

    @property
    def shipping_countries(self):
        shipping_countries = self.pl_supplement.shipping_countries
        target = []
        for country in shipping_countries.all():
            countries = country.locations.split(',')
            for country_splitted in countries:
                target.extend([country_splitted.strip()])
            target.extend([country.slug])

        return target

    @property
    def shipping_groups_string(self):
        return self.pl_supplement.shipping_groups_string


class UserSupplementLabelMixin:

    @property
    def comment_count(self):
        len_comment = self.comments.count()
        if len_comment == 1:
            return "1 comment"
        else:
            return f"{len_comment} comments"

    @property
    def status_string(self):
        for key, value in self.LABEL_STATUSES:
            if self.status == key:
                return value

    @property
    def label_id_string(self):
        return "{}".format(self.id)

    @property
    def is_approved(self):
        return self.status == self.APPROVED

    @property
    def is_awaiting_review(self):
        return self.status == self.AWAITING_REVIEW

    def generate_sku(self):
        self.sku = f"{self.user_supplement.pl_supplement.shipstation_sku}-{self.label_id_string}L"


class LabelCommentMixin:

    @property
    def sets_new_status(self):
        return self.new_status != ''


class PLSOrderMixin:

    @property
    def sale_price_string(self):
        return "${:.2f}".format(self.sale_price / 100.)

    @property
    def profit_string(self):
        return "${:.2f}".format((self.amount - self.wholesale_price) / 100.)

    @property
    def user_profit_string(self):
        return "${:.2f}".format((self.sale_price - self.amount) / 100.)

    @property
    def shipstation_order_number(self):
        return f"{self.order_number}-{self.id}"

    @property
    def shipping_price_string(self):
        return "${:.2f}".format(self.shipping_price / 100.)


class PLSOrderLineMixin:

    @property
    def label_status_string(self):
        def get_string(color, value):
            label = f"<span class='label label-{color}'>{value}</span>"
            return format_html(label)

        if self.is_label_printed:
            return get_string("primary", "Printed")
        else:
            return get_string("default", "Not Printed")

    @property
    def amount_string(self):
        return "${:.2f}".format(self.amount / 100.)

    @classmethod
    def is_paid(cls, store, order_id, line_id):
        return bool(cls.objects.filter(
            store_type=store.store_type,
            store_id=store.id,
            store_order_id=order_id,
            line_id=line_id,
        ).exists())

    def mark_printed(self):
        self.is_label_printed = True
        self.save()

    def mark_not_printed(self):
        self.is_label_printed = False
        self.save()

    @property
    def fulfillment_status_string(self):
        def get_string(color, value):
            label = f"<span class='badge badge-{color}'>{value}</span>"
            return format_html(label)

        if self.pls_order.is_fulfilled:
            return get_string("primary", "Fulfilled")
        else:
            return get_string("warning", "Unfulfilled")


class PayoutMixin:
    @property
    def cost_price(self):
        return sum(self.payout_items.values_list('amount', flat=True))

    @property
    def cost_price_string(self):
        return self.to_currency(self.cost_price)

    @property
    def cost_price_withuot_shipping_string(self):
        return self.to_currency(self.cost_price - self.shipping_price)

    @property
    def wholesale_price(self):
        return sum(self.payout_items.values_list('wholesale_price', flat=True))

    @property
    def wholesale_price_string(self):
        return self.to_currency(self.wholesale_price)

    @property
    def sale_price(self):
        return sum(self.payout_items.values_list('sale_price', flat=True))

    @property
    def sale_price_string(self):
        return self.to_currency(self.sale_price)

    @property
    def shipping_price(self):
        return sum(self.payout_items.values_list('shipping_price', flat=True))

    @property
    def shipping_price_string(self):
        return self.to_currency(self.shipping_price)

    @property
    def profit_split(self):
        profit = self.cost_price - self.wholesale_price - self.shipping_price
        return profit / 3

    @property
    def profit_split_string(self):
        return self.to_currency(self.profit_split)

    @property
    def pls_payout(self):
        return self.profit_split + self.wholesale_price + self.shipping_price

    @property
    def pls_payout_string(self):
        return self.to_currency(self.pls_payout)

    def to_currency(self, value):
        return "${:.2f}".format(value / 100.)


class AuthorizeNetCustomerMixin:
    def charge(self, amount):
        return charge_customer_profile(
            amount,
            self.customer_id,
            self.payment_id,
        )

    def retrieve(self):
        if not self.has_billing():
            return

        try:
            data = get_customer_payment_profile(
                self.customer_id,
                self.payment_id,
            )
        except AttributeError:
            self.payment_id = None
            self.customer_id = None
            self.save()
            return

        self.payment_profile = {
            'credit_card': data.payment.creditCard,
            'bill_to': data.billTo,
        }

    def has_billing(self):
        return bool(self.payment_id)
