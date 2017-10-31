from django.contrib import admin
from .models import *

admin.site.register(RegistrationEvent)
admin.site.register(PlanSelectionEvent)
admin.site.register(BillingInformationEntryEvent)
admin.site.register(SuccessfulPaymentEvent)
