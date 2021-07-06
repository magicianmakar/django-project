import csv
import os
from io import StringIO
from datetime import datetime

import arrow
from lib.exceptions import capture_exception

from django.conf import settings
from django.core.mail import EmailMessage
from django.contrib.auth.models import User
from django.template import Context, Template

from shopified_core.commands import DropifiedBaseCommand
from bigcommerce_core.models import BigCommerceStore
from shopified_core.utils import safe_float

REVENUE_TAX_PERCENT = 20
REVENUE_REPORT_EMAIL = [
    'bigcommerce@dropified.com',
    'weaver@arndtcpas.com'
]


class Command(DropifiedBaseCommand):
    help = 'Generates Tax report for Big Commerce users'

    def add_arguments(self, parser):
        parser.add_argument(
            '-user_id',
            '--user_id',
            default=False,
            help='Process only specified user'
        )

    def start_command(self, *args, **options):
        if arrow.utcnow().day != 1:
            return

        if options['user_id']:
            users = User.objects.filter(pk=options['user_id'])
        else:
            users = User.objects.filter(pk__in=BigCommerceStore.objects.filter(is_active=True).values_list('user', flat=True))

        attachment_csv_file = StringIO()
        writer = csv.writer(attachment_csv_file)

        labels = ['BC App Id', 'BC Store URL', 'BC Store Title', 'User Email', 'User Name', 'Date Joined', 'On Trial',
                  'Client Monthly Revenue', 'Client Monthly Revenue Share', 'Only BigCommerce Connected']
        writer.writerow(labels)

        totals = {"total_bc_stores": 0,
                  "total_only_bc_stores": 0,
                  "total_revenue": 0,
                  "total_revenue_share": 0,
                  "plans": {}}

        # using iterator to minimize memory usage
        for user in users.iterator():
            try:
                active_stores = user.bigcommercestore_set.filter(is_active=True)
                # processing only users with BG stores
                if active_stores.count() > 0 and not user.is_staff and user.email != 'joan@thedevelopmentmachine.com':
                    for bc_store in active_stores:
                        data_item = []
                        data_item.append(settings.BIGCOMMERCE_APP_ID)
                        data_item.append(bc_store.api_url)
                        data_item.append(bc_store.title)
                        data_item.append(user.email)
                        data_item.append(f'{user.first_name} {user.last_name}')
                        data_item.append(user.date_joined.strftime("%Y-%m-%d %H:%M:%S"))
                        monthly_revenue = safe_float(self.get_monthly_revenue(user))
                        if user.profile.on_trial:
                            monthly_revenue_share = 0
                            data_item.append('Yes')
                        else:
                            monthly_revenue_share = safe_float(monthly_revenue / active_stores.count()) * \
                                (safe_float(REVENUE_TAX_PERCENT) / 100)
                            data_item.append('No')
                        if user.email in ['bigninking@gmail.com', 'dgzanezebi@gmail.com', 'matt.crawford@bigcommerce.com', 'online@ksbsol.com'] \
                                or '@dropified.com' in user.email \
                                or '@thedevelopmentmachine.com' in user.email \
                                or user.is_staff:
                            monthly_revenue = 0
                            monthly_revenue_share = 0

                        data_item.append('${:.2f}'.format(monthly_revenue))
                        data_item.append('${:.2f}'.format(monthly_revenue_share))

                        all_stores_count = user.profile.get_stores_count()

                        if user.profile.get_bigcommerce_stores().count() == all_stores_count:
                            data_item.append('Yes')
                            totals['total_only_bc_stores'] += 1
                        else:
                            data_item.append('No')
                        writer.writerow(data_item)

                        totals['total_bc_stores'] += 1
                        totals['total_revenue'] += monthly_revenue
                        totals['total_revenue_share'] += monthly_revenue_share
                        try:
                            totals['plans'][user.profile.plan.id]['total_bc_users'] += 1
                        except:
                            totals['plans'][user.profile.plan.id] = {'title': user.profile.plan.title, 'total_bc_users': 1}

            except:
                capture_exception()

        email_data = {
            'bc_app_id': settings.BIGCOMMERCE_APP_ID,
            'csv_file': attachment_csv_file,
            'report_date': datetime.now(),
            'totals': totals
        }

        for email in REVENUE_REPORT_EMAIL:
            self.send_report(email_data, email)

    def get_monthly_revenue(self, user):
        group_plan = user.profile.plan
        monthly_price = 0
        if group_plan.monthly_price:
            monthly_price = group_plan.monthly_price

        total_stores = user.profile.get_stores_count()
        if total_stores > 0:
            monthly_price = monthly_price / total_stores

        return monthly_price

    def send_report(self, email_data, email_to):
        self.write(f'Sending BigCommerce Report to {email_to}')

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
