from io import BytesIO

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import reverse

import requests
from pdfrw import PdfReader

from lib.exceptions import capture_exception
from shopified_core.management import DropifiedBaseCommand
from shopified_core.utils import send_email_from_template
from supplements.models import UserSupplement


class Command(DropifiedBaseCommand):
    help = 'Leave comment on mismatched label size.'

    def send_email_against_comment(self, comment):
        template = 'label_comment.html'

        label = comment.label
        kwargs = {'supplement_id': label.user_supplement.id}
        history_url = reverse('pls:label_history', kwargs=kwargs)

        subject = f'New comment added to label: {label.id}.'

        data = dict(
            comment=comment,
            product_url=f'{settings.APP_URL}{history_url}'
        )
        recipient = label.user_supplement.user.email

        send_email_from_template(template, subject, recipient, data)

    def start_command(self, *args, **options):
        try:
            for supplement in UserSupplement.objects.exclude(Q(current_label__isnull=True)
                                                             | Q(is_deleted=True)
                                                             | Q(current_label__status='draft')):
                default_label_size = supplement.pl_supplement.label_size
                default_width = '{:.3f}'.format(default_label_size.width)
                default_height = '{:.3f}'.format(default_label_size.height)

                label = supplement.current_label
                label_data = BytesIO(requests.get(label.url).content)
                label_pdf = PdfReader(label_data)
                pdf_dimensions = label_pdf.pages[0].MediaBox
                pdf_width = '{:.3f}'.format(float(pdf_dimensions[2]) / 72)  # pt / 72 = 1 in
                pdf_height = '{:.3f}'.format(float(pdf_dimensions[3]) / 72)

                if not pdf_width == default_width and not pdf_height == default_height:
                    print(f'\n{pdf_width} != {default_width} \n {pdf_height} != {default_height}')
                    user = User.objects.get(id=1)
                    comment_text = (f'Your label does not match the required label size of {default_height}x{default_width} '
                                    'inches. Please reupload your label to match these dimensions.')

                    comment = label.comments.create(
                        user=user,
                        label=label,
                        text=comment_text,
                        new_status='',
                        is_private=False,
                    )

                    self.send_email_against_comment(comment)
        except:
            capture_exception()
