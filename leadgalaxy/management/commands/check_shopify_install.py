import json
from collections import defaultdict

import requests
import arrow

from leadgalaxy.models import ShopifyStore
from shopified_core.commands import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Check Shopify Store Status'
    bar = None

    def add_arguments(self, parser):
        parser.add_argument('--charge', action='store_true', help='Show charge status')
        parser.add_argument('--progress', action='store_true', help='Show progress')

    def start_command(self, *args, **options):
        stores = ShopifyStore.objects.filter(user__profile__plan__payment_gateway='shopify') \
                                     .filter(is_active=True).order_by('id')

        success = 0
        errors = 0
        mrr = 0
        trial = 0
        trial_mrr = 0

        errors_list = []
        charges_count = defaultdict(int)

        self.progress_total(stores.count(), options['progress'])

        for store in stores:
            self.progress_update()

            r = requests.get(store.api('recurring_application_charges'))

            try:
                store_info = json.loads(store.info)
            except:
                store_info = {}

            try:
                store_created_at = arrow.get(store_info.get('created_at')).humanize()
            except:
                store_created_at = ''

            try:
                store_plan = store_info.get('plan_name') or ''
            except:
                store_plan = ''

            if r.ok:
                if not store.is_active:
                    self.write(f'>>> Store {store.shop} should be active')
                    # store.is_active = True
                    # store.save()

                charges = r.json()['recurring_application_charges']
                charges = [c for c in charges if c['status'] == 'active']

                success += 1

                if not len(charges):
                    if not store.user.profile.plan.is_free:
                        self.write(f'>>> Store {store.shop} have {len(charges)} charges but on {store.user.profile.plan.title} | https://app.dropified.com/acp/users/list?q={store.shop}') # noqa
                else:
                    charge = charges[0]
                    trial_ends_on = arrow.get(charge["trial_ends_on"])
                    if charge['test']:
                        success -= 1
                        continue

                    # if trial_ends_on and not store.trial_ends_on:
                    #     self.write(f'> Set trial end on {trial_ends_on.datetime:%d-%m-%Y} for {store.shop}')
                    #     ShopifyStore.objects.filter(id=store.id).update(trial_ends_on=trial_ends_on.datetime)

                    elif trial_ends_on > arrow.utcnow():
                        self.write(f'{charge["price"]}\t{store.shop.ljust(40)}\t{store_plan.ljust(20)}\t{trial_ends_on.humanize()}\t{store_created_at}') # noqa
                        trial += 1
                        trial_mrr += float(charge["price"])
                        charges_count[charge["price"]] -= 1
                    else:
                        # self.write(f'{charge["price"]}\t{store.shop}')
                        pass

                    charges_count[charge["price"]] += 1
                    mrr += float(charge["price"])

                    if store.user.profile.plan.is_free:
                        self.write(f'>>> Store {store.shop} have {len(charges)} charges but on free plan')
                        # store.save()

            else:
                # trial_ends_on = arrow.get(store.trial_ends_on).humanize() if store.trial_ends_on else ''
                errors_list.append(f'{r.status_code}\t{store.shop}\t{store_info.get("plan_name")}\t{store_created_at}')
                errors += 1

                # if store.is_active and r.status_code in [401, 402, 403, 404]:
                #     if not store.user.profile.plan.is_free:
                #         self.write(f'Should be disabled {store.shop}')
                #         store.is_active = False
                #         store.save()

        self.progress_close()

        # if errors_list:
        #    self.write('\nError Stores:')
        #    self.write('\n'.join(errors_list))

        lines = ['\n']
        if mrr:
            net_mrr = mrr - (mrr * 0.2)
            net_trial_mrr = trial_mrr - (trial_mrr * 0.2)
            net_revenue = net_mrr - net_trial_mrr
            lines.append(f'MRR:     ${net_mrr:.2f} (${mrr:.2f})')
            lines.append(f'Trial:   ${net_trial_mrr:.2f} (${trial_mrr:.2f})')
            lines.append(f'Net MRR: ${net_revenue:.2f} (${mrr - trial_mrr:.2f})')

        lines.append(f'\nStores {success}\n\tActive: {success - trial}\n\tTrial: {trial}\n\tErrors: {errors}')

        self.write('\n'.join(lines))
