from django.contrib.auth.decorators import login_required

from django.shortcuts import render
from django.utils import timezone
from datetime import timedelta


@login_required
def fees_list(request):

    if request.user.can('sales_fee.use') and (request.user.is_superuser or not request.user.can('disabled_sales_fee.use')):
        exp_date = timezone.now() + timedelta(days=-90)

        fees = request.user.saletransactionfee_set.filter(created_at__gte=exp_date).order_by('created_at')
    else:
        fees = []

    return render(request, 'fulfilment_fee/fees_list.html', {'fees': fees})
