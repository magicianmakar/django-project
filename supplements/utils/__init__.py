from django.conf import settings
from django.shortcuts import reverse

from shopified_core.utils import do_create_aws_s3_context, send_email_from_template


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
    kwargs = {'supplement_id': label.user_supplement.id}
    history_url = reverse('pls:label_history', kwargs=kwargs)

    subject = f'New comment added to label: {label.label_id_string}.'
    if comment.new_status == label.APPROVED:
        subject = f'Label {label.label_id_string} was approved.'

    elif comment.new_status == label.REJECTED:
        subject = f'Label {label.label_id_string} was rejected.'

    data = dict(
        comment=comment,
        product_url=f'{settings.APP_URL}{history_url}'
    )
    recipient = label.user_supplement.user.email

    return send_email_from_template(template, subject, recipient, data)


def aws_s3_context():
    conditions = [
        ["starts-with", "$utf8", ""],
        # Change this path if you need, but adjust the javascript config
        ["starts-with", "$key", "uploads"],
        ["starts-with", "$name", ""],
        ["starts-with", "$Content-Type", "application/"],
        ["starts-with", "$filename", ""],
        {"bucket": settings.AWS_STORAGE_BUCKET_NAME},
        {"acl": "public-read"}
    ]

    return do_create_aws_s3_context(conditions)


def user_can_download_label(user, label):
    user_is_owner = user.models_user == label.user_supplement.user.models_user
    user_is_supplier = user.supplies(label.user_supplement.pl_supplement)
    if user.can('pls_admin.use') or user.can('pls_staff.use') or user_is_owner or user_is_supplier:
        return True
    return False


def supplement_customer_address(address):
    mapped_country_codes = {'United States': 'US', 'UK': 'GB'}
    if address.get('country_code'):
        country_code = address['country_code']
        address['country_code'] = mapped_country_codes.get(country_code, country_code)

    mapped_countries = {'TW': 'Taiwan'}
    if address.get('country_code') and address.get('country'):
        address['country'] = mapped_countries.get(address['country_code'], address['country'])

    return address
