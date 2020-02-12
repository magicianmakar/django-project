from shopified_core.utils import send_email_from_template


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
