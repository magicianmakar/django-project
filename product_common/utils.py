from shopified_core.utils import send_email_from_template
from supplements.models import PLSReview
from django.db.models import Avg, Count
import json


def create_rows(items, row_size):
    batch = []
    for i in items:
        batch.append(i)
        if len(batch) == row_size:
            yield batch
            batch = []

    if batch:
        yield batch


def send_email_against_comment(comment):
    template = 'label_comment.html'

    label = comment.label

    subject = f'New comment added to label: {label.label_id_string}.'
    if comment.new_status == label.APPROVED:
        subject = f'label {label.label_id_string} was approved.'

    elif comment.new_status == label.REJECTED:
        subject = f'label {label.label_id_string} was rejected.'

    data = dict(comment=comment)
    recipient = label.user_supplement.user.email

    return send_email_from_template(template, subject, recipient, data)


def get_order_reviews(user, orders):
    new_tracker_orders = []
    for order in orders:
        review = PLSReview.objects.filter(
            pls_order_line__order_track_id=order.id,
            user=user).first()
        if review:
            order.review = True
        new_tracker_orders.append(order)
    return new_tracker_orders


def get_product_reviews(supplements):
    supplements_with_reviews = []
    for supplement in supplements:
        supplement_reviews = PLSReview.objects.filter(pl_supplement=supplement.id)
        reviews = json.dumps(list(supplement_reviews.exclude(comment="").values(
            'user__first_name', 'user__last_name', 'product_quality_rating', 'label_quality_rating', 'delivery_rating', 'comment')))
        reviews_agg = supplement_reviews.aggregate(
            count=Count('pl_supplement'),
            pq_rating=Avg('product_quality_rating'),
            lq_rating=Avg('label_quality_rating'),
            dl_rating=Avg('delivery_rating')
        )
        if reviews_agg['count'] > 5:
            supplement.supplement_reviews = reviews
            supplement.product_quality_rating = round(reviews_agg['pq_rating'] / 5 * 100, 1)
            supplement.label_quality_rating = round(reviews_agg['lq_rating'] / 5 * 100, 1)
            supplement.delivery_rating = round(reviews_agg['dl_rating'] / 5 * 100, 1)
            supplement.avg_rating = round(
                (reviews_agg['pq_rating'] + reviews_agg['lq_rating'] + reviews_agg['dl_rating']) / 3, 1)
            supplement.count = reviews_agg['count']
        supplements_with_reviews.append(supplement)
    return supplements_with_reviews
