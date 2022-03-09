import json
import time
from collections import defaultdict

from django.test import RequestFactory

from alibaba_core.models import AlibabaAccount, AlibabaOrder
from alibaba_core.utils import APIRequest, save_alibaba_products
from lib.exceptions import capture_exception, capture_message
from shopified_core.commands import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Consume/Confirm Alibaba Messages'

    def confirm_messages(self, s_message_ids):
        api = APIRequest(None)
        response = api.get(resource='taobao.tmc.messages.confirm', params={
            's_message_ids': ','.join([str(i) for i in s_message_ids]),
        })
        success = response['tmc_messages_confirm_response']['is_success']

        if not success:
            capture_message('Alibaba messages not succeeded', extra={'ids': s_message_ids, 'response': response})

    def run_api_call(self, *args, **options):
        products_data = defaultdict(list)

        api = APIRequest(None)
        response = api.get(resource='taobao.tmc.messages.consume', params={
            'quantity': 100,
        })
        if 'error' in response or not response:
            raise Exception(response and response['error'] or 'Error consuming alibaba messages')

        messages = response['tmc_messages_consume_response']['messages']
        if messages:
            self.confirm_messages([m['id'] for m in messages['tmc_message']])
            for message in messages['tmc_message']:
                if message['topic'] == 'icbu_trade_ProductNotify':
                    alibaba_user_id = message['user_id']
                    content = json.loads(message['content'])
                    accounts = AlibabaAccount.objects.filter(alibaba_user_id=alibaba_user_id)
                    if not accounts:
                        capture_message(
                            'Alibaba Account does not exist.',
                            extra={'alibaba_user_id': alibaba_user_id}
                        )
                        continue
                    for account in accounts:
                        products_data[account.user.id].append(content['product_id'])

                if message['topic'] == 'icbu_trade_OrderNotify':
                    content = json.loads(message['content'])
                    orders = AlibabaOrder.objects.prefetch_related('items').filter(trade_id=content['trade_id'])
                    for order in orders:
                        order.reload_details()
                        order.handle_tracking()

        request = RequestFactory().get('/')
        save_alibaba_products(request, products_data)

    def start_command(self, *args, **options):
        while True:
            start_time = time.time()
            try:
                self.run_api_call()

            except:
                capture_exception()

            time_left = 15 - int(time.time() - start_time)
            time.sleep(time_left if time_left > 0 else 0)
