from django.contrib import admin

from .models import TapfiliateCommissions
from stripe_subscription.models import StripeCustomer


@admin.register(TapfiliateCommissions)
class TapfiliateCommissionsAdmin(admin.ModelAdmin):
    list_display = ('commission_id', 'conversion_id', 'affiliate_id', 'charge_id', 'customer_id', 'customer_email', 'created_at', 'updated_at')
    search_fields = ('commission_id', 'conversion_id', 'affiliate_id', 'charge_id', 'customer_id')
    list_filter = ('affiliate_id', 'created_at', 'updated_at')

    def customer_email(self, inst):
        return StripeCustomer.objects.get(customer_id=inst.customer_id).user.email
