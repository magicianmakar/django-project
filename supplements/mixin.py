from authorizenet import apicontractsv1
from django.db.models import F, Sum
from django.shortcuts import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html

import simplejson as json
from bs4 import BeautifulSoup

from supplements.lib.authorizenet import (
    charge_customer_profile,
    get_customer_payment_profile,
    refund_customer_profile,
    charge_customer_for_items,
    void_unsettled_transaction,
    retrieve_transaction_status,
)


class PLSupplementMixin:
    is_admin_editable = True

    @cached_property
    def thumbnail(self):
        first_image = self.images.all().order_by('position').first()
        return first_image.image_url if first_image else ''

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

    @cached_property
    def shipping_locations(self):
        target = []
        for country in self.pl_supplement.shipping_countries.all():
            for country_splitted in country.locations.split(','):
                target.extend([country_splitted.strip()])
            target.extend([country.slug])

        return target

    @property
    def shipping_groups_string(self):
        return self.pl_supplement.shipping_groups_string

    @property
    def labels_comment_count(self):
        len_comment = 0
        for label in self.labels.all():
            len_comment += label.comments.count()

        if len_comment == 1:
            return "1 comment"
        else:
            return f"{len_comment} comments"

    def get_seen_users_list(self):
        try:
            seen_users = json.loads(self.seen_users)
        except json.errors.JSONDecodeError:
            seen_users = []

        return seen_users

    def mark_as_read(self, user_id):
        seen_users = self.get_seen_users_list()
        if user_id not in seen_users:
            seen_users.append(user_id)
            self.seen_users = json.dumps(seen_users)
            self.save()

    def mark_as_unread(self, user_id):
        self.seen_users = json.dumps([user_id])
        self.save()

    @property
    def is_supplement_deleted(self):
        return self.is_deleted


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
    def created_at_string(self):
        return self.created_at.strftime('%m.%d.%Y %H:%M')

    @property
    def updated_at_string(self):
        return self.updated_at.strftime('%m.%d.%Y %H:%M')

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
    def created_at_string(self):
        return self.created_at.strftime('%m.%d.%Y %H:%M')

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

    @property
    def item_total(self):
        result = self.order_items.aggregate(total=Sum(F('amount') * F('quantity')))
        return "${:.2f}".format(result['total'] / 100.)

    @property
    def amount_without_refund(self):
        amount = self.amount / 100.
        if self.refund:
            amount -= float(self.refund_amount)

        return amount

    @property
    def amount_without_refund_string(self):
        return '${:.2f}'.format(self.amount_without_refund)

    @property
    def refund_amount(self):
        refund = 0
        if self.refund:
            refund = self.refund.amount - self.refund.fee

        return refund

    @property
    def refund_amount_string(self):
        return '${:.2f}'.format(self.refund_amount)

    @property
    def refund_fee(self):
        fee = 0
        if self.refund:
            fee = self.refund.fee

        return fee

    @property
    def refund_fee_string(self):
        return '${:.2f}'.format(self.refund_fee)

    @property
    def shipping_refund(self):
        shipping = 0
        if self.refund:
            shipping = self.refund.shipping

        return shipping

    @property
    def shipping_refund_string(self):
        return '${:.2f}'.format(self.shipping_refund)

    @property
    def total_refund_amount_string(self):
        return '${:.2f}'.format(self.refund_amount + self.shipping_refund)

    @property
    def order_refund_id(self):
        if self.refund:
            return self.refund.transaction_id

    @property
    def is_taxes_paid(self):
        return (self.taxes + self.duties) > 0


class PLSOrderLineMixin:

    @property
    def label_status_string(self):
        def get_string(color, value):
            label = f"<span class='badge badge-{color}'>{value}</span>"
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
            line_id__startswith=line_id,
        ).exists())

    @classmethod
    def get_shipstation_key(cls, store_type, store_id, order_id, line_id, label_id):
        return f'{store_type}-{store_id}-{order_id}-{line_id}-{label_id}'

    def mark_printed(self):
        self.is_label_printed = True
        self.save()

    def mark_not_printed(self):
        self.is_label_printed = False
        self.save()

    @property
    def is_refunded(self):
        if self.refund_amount:
            return True

        return False

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
    @cached_property
    def cost_price(self):
        return sum(self.payout_lines.values_list('pls_order__amount', flat=True))

    @property
    def cost_price_string(self):
        return self.to_currency(self.cost_price)

    @property
    def cost_price_withuot_shipping_string(self):
        return self.to_currency(self.cost_price - self.order_shipping_price)

    @cached_property
    def wholesale_price(self):
        return sum(self.payout_lines.values_list('pls_order__wholesale_price', flat=True))

    @property
    def wholesale_price_string(self):
        return self.to_currency(self.wholesale_price)

    @cached_property
    def sale_price(self):
        return sum(self.payout_lines.values_list('pls_order__sale_price', flat=True))

    @property
    def sale_price_string(self):
        return self.to_currency(self.sale_price)

    @cached_property
    def order_shipping_price(self):
        return sum(self.payout_lines.values_list('pls_order__shipping_price', flat=True))

    @cached_property
    def shipping_price(self):
        return sum(self.ship_payout_lines.values_list('pls_order__shipping_price', flat=True))

    @property
    def shipping_price_string(self):
        return self.to_currency(self.shipping_price)

    @cached_property
    def total_shipping(self):
        shipping = self.shipping_price - (int(self.shipping_refund) * 100)
        if self.shipping_cost:
            shipping -= self.shipping_cost

        return shipping

    @property
    def total_shipping_string(self):
        return self.to_currency(self.total_shipping)

    @cached_property
    def profit_split(self):
        price = self.cost_price - self.wholesale_price - self.order_shipping_price
        price = price - (int(self.refund_amount) * 100)
        if self.shipping_cost:
            price -= self.shipping_cost

        return price

    @property
    def dropified_profit_split_string(self):
        commission = float(self.supplier.get_dropified_commission()) / 100.
        if self.supplier.is_shipping_supplier:
            split = self.total_shipping * commission
        else:
            split = (self.profit_split * commission) + (self.total_shipping * commission)

        return self.to_currency(split)

    @property
    def tlg_profit_split_string(self):
        commission = float(self.supplier.get_tlg_commission()) / 100.
        if self.supplier.is_shipping_supplier:
            split = self.total_shipping * commission
        else:
            split = (self.profit_split * commission) + (self.total_shipping * commission)

        return self.to_currency(split)

    @property
    def supplier_profit_split_string(self):
        commission = float(self.supplier.profit_percentage) / 100.
        if self.supplier.is_shipping_supplier:
            split = self.total_shipping * commission
        else:
            split = (self.profit_split * commission) + (self.total_shipping * commission)

        return self.to_currency(split)

    @cached_property
    def profit_string(self):
        return self.to_currency(self.profit_split)

    @cached_property
    def supplier_payout(self):
        commission = float(self.supplier.profit_percentage) / 100.
        price = (self.profit_split * commission) + self.wholesale_price
        if self.shipping_cost:
            price += self.shipping_cost

        return price

    @property
    def supplier_payout_string(self):
        commission = float(self.supplier.profit_percentage) / 100.
        if self.supplier.is_shipping_supplier:
            payout = (self.total_shipping * commission)
            if self.shipping_cost:
                payout += self.shipping_cost
        else:
            payout = self.supplier_payout + (self.total_shipping * commission)

        return self.to_currency(payout)

    @cached_property
    def shipping_cost_string(self):
        if self.shipping_cost:
            return self.to_currency(self.shipping_cost)

        return '$0.00'

    @cached_property
    def refund_amount(self):
        refund = 0
        for line in self.payout_lines.all():
            refund += line.pls_order.refund_amount

        return refund

    @property
    def refund_amount_string(self):
        return '${:.2f}'.format(self.refund_amount)

    @cached_property
    def shipping_refund(self):
        refund = 0
        for line in self.ship_payout_lines.all():
            refund += line.pls_order.shipping_refund

        return refund

    @property
    def shipping_refund_string(self):
        return '${:.2f}'.format(self.shipping_refund)

    @property
    def date_from_to(self):
        try:
            lines = self.payout_lines
            if self.supplier.is_shipping_supplier:
                lines = self.ship_payout_lines
            date_from = lines.first().created_at.strftime('%m.%d.%Y')
            date_to = lines.last().created_at.strftime('%m.%d.%Y')
            return f'{date_from} - {date_to}'
        except:
            return ''

    def to_currency(self, value):
        return "${:.2f}".format(value / 100)


class AuthorizeNetCustomerMixin:
    @cached_property
    def customer_profile(self):
        customer_profile = apicontractsv1.customerProfilePaymentType()
        customer_profile.customerProfileId = self.customer_id

        customer_profile.paymentProfile = apicontractsv1.paymentProfile()
        customer_profile.paymentProfile.paymentProfileId = self.payment_id

        return customer_profile

    def charge(self, amount, line):
        return charge_customer_profile(
            amount,
            self.customer_id,
            self.payment_id,
            line,
        )

    def refund(self, amount, transaction_id):
        return refund_customer_profile(
            amount,
            self.customer_id,
            self.payment_id,
            transaction_id,
        )

    def void(self, transaction_id):
        return void_unsettled_transaction(
            self.customer_id,
            self.payment_id,
            transaction_id,
        )

    def status(self, transaction_id):
        return retrieve_transaction_status(
            self.customer_id,
            transaction_id,
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

    def get_transaction(self, transanction_type='authCaptureTransaction'):
        transaction = apicontractsv1.transactionRequestType()
        transaction.transactionType = transanction_type
        transaction.profile = self.customer_profile
        return transaction

    def charge_items(self, line_items):
        return charge_customer_for_items(
            self.get_transaction(),
            line_items
        )
