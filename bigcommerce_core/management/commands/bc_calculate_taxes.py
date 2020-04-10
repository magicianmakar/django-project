from django.contrib.auth.models import User
from shopified_core.management import DropifiedBaseCommand
from bigcommerce_core.models import BigCommerceStore

from raven.contrib.django.raven_compat.models import client as raven_client
from django.conf import settings
from django.core.mail import EmailMessage
from datetime import datetime
import csv
from io import StringIO
import os
from django.template import Context, Template
from shopified_core.utils import safe_float


class Command(DropifiedBaseCommand):
    help = 'Generates Tax report for Big Commerce users'

    def add_arguments(self, parser):
        parser.add_argument(
            '-email',
            '--email',
            default=settings.BIGCOMMERCE_REVENUE_REPORT_EMAIL,
            help='email to send report to'
        )
        parser.add_argument(
            '-user_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

    def start_command(self, *args, **options):
        if options['user_id']:
            users = User.objects.filter(pk=options['user_id'])
        else:
            users = User.objects.filter(pk__in=BigCommerceStore.objects.values_list('user', flat=True))

        attachment_csv_file = StringIO()
        writer = csv.writer(attachment_csv_file)

        labels = ['BC App Id', 'BC Store URL', 'BC Store Title', 'User Email', 'User Name', 'Date Joined', 'On Trial',
                  'Client Monthly Revenue', 'Client Monthly Revenue Share']
        writer.writerow(labels)

        totals = {"total_bc_stores": 0,
                  "total_revenue": 0,
                  "total_revenue_share": 0}

        # using iterator to minimize memory usage
        for user in users.iterator():
            try:
                active_stores = user.bigcommercestore_set.filter(is_active=True)
                # processing only users with BG stores
                if active_stores.count() > 0:
                    self.write(f"Processing User ID:{user.pk} ")
                    for bc_store in active_stores:
                        data_item = []
                        data_item.append(settings.BIGCOMMERCE_APP_ID)
                        data_item.append(bc_store.api_url)
                        data_item.append(bc_store.title)
                        data_item.append(user.email)
                        data_item.append(user.first_name + " " + user.last_name)
                        data_item.append(user.date_joined.strftime("%Y-%m-%d %H:%M:%S"))
                        monthly_revenue = safe_float(self.get_monthly_revenue(user))
                        if user.profile.on_trial:
                            monthly_revenue_share = 0
                            data_item.append('Yes')
                        else:
                            monthly_revenue_share = safe_float(monthly_revenue / active_stores.count()) * \
                                (safe_float(settings.BIGCOMMERCE_REVENUE_TAX_PERCENT) / 100)
                            data_item.append('No')
                        data_item.append('${:.2f}'.format(monthly_revenue))
                        data_item.append('${:.2f}'.format(monthly_revenue_share))
                        writer.writerow(data_item)

                        totals['total_bc_stores'] += 1
                        totals['total_revenue'] += monthly_revenue
                        totals['total_revenue_share'] += monthly_revenue_share
            except:
                raven_client.captureException()

        email_data = {
            'bc_app_id': settings.BIGCOMMERCE_APP_ID,
            'csv_file': attachment_csv_file,
            'report_date': datetime.now(),
            'totals': totals
        }
        self.send_report(email_data, options['email'])

    @staticmethod
    def get_monthly_revenue(user):
        group_plan = user.profile.plan
        monthly_price = 0
        if group_plan.monthly_price:
            monthly_price = group_plan.monthly_price

        total_stores = user.profile.get_stores_count()
        if total_stores > 0:
            monthly_price = monthly_price / total_stores

        return monthly_price

    @staticmethod
    def send_report(email_data, email_to):
        template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', 'bc_taxes_report.html')
        template = Template(open(template_file).read())
        ctx = Context(email_data)
        email_html = template.render(ctx)
        # using EmailMessage for file atachements
        email = EmailMessage('BigCommerce Revenue Report', email_html, '"Dropified" <support@dropified.com>',
                             [email_to], [])
        email.content_subtype = "html"
        email.attach('BC_report_{}.csv'.format(datetime.now().strftime("%Y_%m_%d")),
                     email_data['csv_file'].getvalue().encode(), 'application/octet-stream')
        email.send(fail_silently=False)
