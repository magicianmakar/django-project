from django.contrib.auth.decorators import login_required

from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta
from fulfilment_fee import utils
import datetime
import calendar


@login_required
def fees_list(request):

    if request.user.can('sales_fee.use') and (request.user.is_superuser or not request.user.can('disabled_sales_fee.use')):
        exp_date = timezone.now() + timedelta(days=-90)

        fees = request.user.saletransactionfee_set.filter(created_at__gte=exp_date).order_by('created_at')
    else:
        fees = []

    date = timezone.now()
    date_from = date.replace(day=1, hour=0, minute=0, second=0)
    date_to = date_from.replace(day=1) + datetime.timedelta(days=calendar.monthrange(date.year, date.month)[1] - 1)

    total_orders_this_month = utils.get_total_orders(request.user)
    total_fees_this_month = utils.get_total_fees(request.user)
    monthly_free_limit = request.user.profile.plan.sales_fee_config.monthly_free_limit

    return render(request, 'fulfilment_fee/fees_list.html', {'fees': fees, 'date_from': date_from, 'date_to': date_to,
                                                             'total_orders_this_month': total_orders_this_month,
                                                             'total_fees_this_month': total_fees_this_month,
                                                             'monthly_free_limit': monthly_free_limit})
