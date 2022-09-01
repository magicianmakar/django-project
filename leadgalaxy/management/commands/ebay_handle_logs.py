import datetime

from shopified_core.commands import DropifiedBaseCommand
from suredone_core.api import SureDoneAdminApiHandler, SureDoneApiHandler


class Command(DropifiedBaseCommand):
    help = 'Create a list of ebay shops that have failing requests, after that disable these failing instances'

    def add_arguments(self, parser):
        parser.add_argument(
            '--failreq', dest='failreq', action='store', type=int, default=10,
            help='How many failing requests to disable a store')

        parser.add_argument(
            '--days', dest='days', action='store', type=int, default=28,
            help='Days limit for check logs')

        parser.add_argument(
            '--operation', dest='operation', action='store', type=str, default='',
            help='Type of error that looking for in logs')

    def start_command(self, *args, **options):
        failing_requests = options.get('failreq') if options.get('failreq') else 100
        operation = options.get('operation') if options.get('operation') else ''
        days = options.get('days') if options.get('days') else 7

        # Set filters
        timestamp_end = datetime.date.today()
        timestamp_start = datetime.date.today() - datetime.timedelta(days)
        total_store_instance_errors = 0
        total_errors = 0
        total_operation_errors = []

        data = {
            'context': 'ebay',
            'result': 'error',
            'operation': operation,
            'timestamp_start': timestamp_start.strftime('%Y-%m-%dT00:00:00'),
            'timestamp_end': timestamp_end.strftime('%Y-%m-%dT00:00:00'),
            'records': '50'
        }
        self.write('Handle ebay error logs is starting')
        self.write(f'Its working for {days} days')

        # Get all SureDone users
        users = SureDoneAdminApiHandler.list_all_users()
        all_suredone_users = users.get('users')

        # Get SureDone users logs
        if len(all_suredone_users):
            for item in range(len(all_suredone_users)):
                suredone_user = all_suredone_users.get(f'{item+1}')
                if suredone_user:
                    api_username = suredone_user.get('name')
                    api_token = suredone_user.get('token')
                    suredone_user_log_records = SureDoneApiHandler(api_username=api_username, api_token=api_token).get_logs(data=data)
                    store_instances = set()

                    if suredone_user_log_records and suredone_user_log_records.get('found') > failing_requests:
                        total_errors += suredone_user_log_records.get('found')
                        suredone_user_logs = suredone_user_log_records.get('logs')
                        store_instances = set([log.get('instance') for log in suredone_user_logs.values()])
                        total_store_instance_errors += len(store_instances)
                        operation_errors = [log.get('operation') for log in suredone_user_logs.values()]
                        total_operation_errors.extend(operation_errors)

                    try:
                        self.disable_store_instance(api_username, api_token, store_instances)
                        self.write(f'{len(store_instances)} channels of {api_username} has been disabled')
                    except:
                        self.write(f'Something went wrong: {len(store_instances)} channels of {api_username} has not been disabled')

            total_operation_errors = set(total_operation_errors)

            if total_errors == 1:
                self.write(f'Found {total_errors} error')
                self.write(f'The operation of error is {total_operation_errors}')
            else:
                self.write(f'Found {total_errors} errors in {total_store_instance_errors} stores')
                if len(total_operation_errors):
                    self.write(f'The operation of errors are: {total_operation_errors}')

        else:
            self.write("There aren't users for SureDone")
            return

        self.write('Handle ebay error logs ends')
        return

    def disable_store_instance(self, api_username, api_token, store_instances):

        sd_api_request_data = {}
        for store_instance in store_instances:
            ebay_prefix = f'ebay{store_instance}' if store_instance else 'ebay'
            sd_api_request_data.update({
                f'site_{ebay_prefix}connect': 'off',
                f'{ebay_prefix}_description_about': 'Channel has been disabled by errors'
            })

        return SureDoneApiHandler(api_username=api_username, api_token=api_token).update_settings(sd_api_request_data)
