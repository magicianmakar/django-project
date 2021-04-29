from django.db import transaction
from django.template.defaultfilters import slugify

from leadgalaxy.models import GroupPlan
from shopified_core.management import DropifiedBaseCommand
from stripe_subscription.models import StripePlan


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Remove data from the database, otherwise report numbers')

    def get_float(self, desc, default=0.0):
        try:
            return float(input(f'{desc.strip()} '))
        except:
            return default

    def get_int(self, desc, default=0):
        try:
            return int(input(f'{desc.strip()} '))
        except:
            return default

    def start_command(self, *args, **options):
        plan_name = input('Plan Name: ')
        plan_name_visible_to_users = input('Plan name visible to users: ')

        gateways = ['stripe', 'shopify', 'jvzoo']
        intervals = ['monthly', 'yearly', 'lifetime']
        self.write('\n[*] Payement details (multi comma separated values)')
        payment_gateway = [i.strip() for i in input(f'Payment gateway: [{",".join(gateways)}] (multi comma separated) ').split(',')]
        payment_interval = [i.strip() for i in input(f'Payment interval: [{",".join(intervals)}] (multi comma separated) ').split(',')]

        for i in payment_gateway:
            if i not in gateways:
                raise Exception(f'Unknow gateway {i}')

        for i in payment_interval:
            if i not in intervals:
                raise Exception(f'Unknow gateway {i}')

        self.write('\n[*] Plan Limits')
        stores_limit = self.get_float('Stores Limit:')
        products_limit = self.get_float('Products Limit:')
        boards_limit = self.get_float('Boards Limit:')
        auto_fulfill_limit = self.get_float('Auto Fulfill Limit:')
        unique_supplements_limit = self.get_float('Unique Supplements Limit:')
        user_supplements_limit = self.get_float('User Supplements Limit:')

        self.write('\n[*] Extra Stores')
        support_adding_extra_stores = input('Support adding extra stores? [N/y] ') == 'y'
        extra_store_cost = self.get_float('Extra store cost per store:') if support_adding_extra_stores else 27.00

        support_addons = input('Support Addons? [N/y] ') == 'y'

        free_plan = input('Free plan? [N/y] ') == 'y'
        trial_days = self.get_int('Trial days: ') if not free_plan else 0
        monthly_price = self.get_float('Monthly Price:') if 'monthly' in payment_interval else 0.00
        yearly_price = self.get_float('Yearly Price:') if 'yearly' in payment_interval else 0.00
        lifetime_price = self.get_float('Lifetime Price:') if 'lifetime' in payment_interval else 0.00

        with transaction.atomic():
            for gateway in payment_gateway:
                for interval in payment_interval:
                    name = plan_name
                    price = 0.00

                    if free_plan:
                        name = f'{name} Free'
                    elif interval == 'monthly':
                        name = f'{name} Monthly'
                        price = monthly_price
                    elif interval == 'yearly':
                        name = f'{name} Yearly'
                        price = yearly_price / 12.0
                    elif interval == 'lifetime':
                        name = f'{name} Lifetime'
                        price = lifetime_price

                    if gateway == 'shopify':
                        name = f'{name} Shopify'

                    slug = slugify(name)

                    plan = GroupPlan.objects.create(
                        title=name,
                        description=plan_name_visible_to_users,
                        slug=slug,

                        stores=stores_limit,
                        products=products_limit,
                        boards=boards_limit,
                        unique_supplements=unique_supplements_limit,
                        user_supplements=user_supplements_limit,
                        auto_fulfill_limit=auto_fulfill_limit,

                        extra_stores=support_adding_extra_stores,
                        extra_store_cost=extra_store_cost,

                        support_addons=support_addons,

                        monthly_price=price,
                        free_plan=free_plan,
                        trial_days=trial_days,

                        payment_gateway=gateway,
                        payment_interval=interval,
                        hidden=True,
                        locked=True,
                    )

                    if gateway == 'stripe':
                        self.create_stripe_plan(plan, monthly_price, yearly_price)

                    self.write(f'Plan {plan.title} created (id: {plan.id})')

    def create_stripe_plan(self, plan, monthly_price, yearly_price):
        amount = 0.00
        interval = None

        if plan.payment_interval == 'monthly':
            amount = monthly_price
            interval = 'month'

        elif plan.payment_interval == 'yearly':
            amount = yearly_price
            interval = 'year'

        else:
            interval = 'month'

        StripePlan.objects.create(
            name=plan.title,
            plan=plan,
            amount=amount,
            retail_amount=0.00,

            interval=interval,
            trial_period_days=plan.trial_days,
        )
