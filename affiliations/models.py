import pytz

from django.contrib.auth.models import User
from django.db import models
from django.utils.functional import cached_property

from dateutil import relativedelta


class LeadDynoAffiliate(models.Model):
    user = models.OneToOneField(User, null=True, related_name='lead_dyno_affiliation')
    affiliation_id = models.BigIntegerField()
    email = models.CharField(max_length=255)
    first_name = models.CharField(max_length=255, default='', null=True)
    last_name = models.CharField(max_length=255, default='', null=True)
    affiliate_dashboard_url = models.CharField(max_length=512)
    affiliate_url = models.CharField(max_length=512)

    def parse_monthly_resources(self, resource):
        finished_list = []

        first_month, last_month = self.resources_lifetime
        latest_month = resource.first()['month'] if resource.first() is not None else first_month

        difference = relativedelta.relativedelta(latest_month, first_month)
        finished_list += [0] * difference.months

        for item in resource:
            finished_list.append(item['count'])

            current_month = item['month']
            difference = relativedelta.relativedelta(current_month, latest_month)

            finished_list += [0] * (difference.months - 1)
            latest_month = current_month

        difference = relativedelta.relativedelta(last_month, latest_month)
        finished_list += [0] * difference.months

        return {
            'values': finished_list,
            'start': first_month,
            'end': last_month,
        }

    @cached_property
    def resources_lifetime(self):
        if self.visitors.last() is None:
            from django.utils import timezone

            today = timezone.now()
            return today.replace(month=1, day=1, hour=0, minute=0, second=0), \
                today.replace(day=1, hour=0, minute=0, second=0)

        start = min([
            self.visitors.last().created_at,
            self.leads.last().created_at,
            self.purchases.last().created_at
        ])

        end = max([
            self.visitors.first().created_at,
            self.leads.first().created_at,
            self.purchases.first().created_at
        ])

        return start.replace(day=1, hour=0, minute=0, second=0), \
            end.replace(day=1, hour=0, minute=0, second=0)

    @cached_property
    def monthly_visitors(self):
        result = self.visitors.annotate(month=models.expressions.DateTime('created_at', 'month', pytz.UTC)) \
                              .values('month') \
                              .annotate(count=models.Count('id')) \
                              .order_by('month')

        return self.parse_monthly_resources(result)

    @cached_property
    def monthly_leads(self):
        result = self.leads.annotate(month=models.expressions.DateTime('created_at', 'month', pytz.UTC)) \
                           .values('month') \
                           .annotate(count=models.Count('id')) \
                           .order_by('month')

        return self.parse_monthly_resources(result)

    @cached_property
    def monthly_purchases(self):
        result = self.purchases.annotate(month=models.expressions.DateTime('created_at', 'month', pytz.UTC)) \
                               .values('month') \
                               .annotate(count=models.Count('id')) \
                               .order_by('month')

        return self.parse_monthly_resources(result)


class LeadDynoVisitor(models.Model):
    affiliate = models.ForeignKey(LeadDynoAffiliate, null=True, related_name='visitors', on_delete=models.SET_NULL)
    affiliate_email = models.CharField(max_length=255, default='')
    original_data = models.TextField()
    visitor_id = models.BigIntegerField()
    created_at = models.DateTimeField()
    tracking_code = models.CharField(max_length=64)
    url = models.CharField(max_length=512)

    class Meta:
        ordering = ['-created_at']


class LeadDynoLead(models.Model):
    affiliate = models.ForeignKey(LeadDynoAffiliate, null=True, related_name='leads', on_delete=models.SET_NULL)
    affiliate_email = models.CharField(max_length=255, default='')
    original_data = models.TextField()
    lead_id = models.BigIntegerField()
    email = models.CharField(max_length=512, blank=True, default='')
    created_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']


class LeadDynoPurchase(models.Model):
    affiliate = models.ForeignKey(LeadDynoAffiliate, null=True, related_name='purchases', on_delete=models.SET_NULL)
    affiliate_email = models.CharField(max_length=255, default='')
    original_data = models.TextField()
    purchase_id = models.BigIntegerField()
    purchase_code = models.CharField(max_length=100)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']


class LeadDynoSync(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    last_synced_visitor = models.ForeignKey(LeadDynoVisitor, null=True)
    last_synced_lead = models.ForeignKey(LeadDynoLead, null=True)
    last_synced_purchase = models.ForeignKey(LeadDynoPurchase, null=True)
    count_visitors = models.IntegerField(default=0)
    count_leads = models.IntegerField(default=0)
    count_purchases = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
