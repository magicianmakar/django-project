import json
import re
import time
from io import StringIO

from django.contrib.auth.models import User

import arrow
import boto3
import logfmt

from leadgalaxy.utils import aws_s3_upload
from shopified_core.management import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Generate user activity log'

    def add_arguments(self, parser):
        parser.add_argument('user', type=str, help='User Email or ID')

    def start_command(self, *args, **options):
        user_id = options['user']

        try:
            user = User.objects.get(id=int(user_id))
        except ValueError:
            user = User.objects.get(email__iexact=user_id)

        self.write(f'Activity log for {user.email}')
        url = self.generate_results(user)

        self.write(f'Log URL: {url}')

    def fetchall_athena(self, query_string):
        client = boto3.client('athena', 'us-east-1')

        query_id = client.start_query_execution(
            QueryString=query_string,
            QueryExecutionContext={
                'Database': 'shopifiedapplogs'
            },
            ResultConfiguration={
                'OutputLocation': 's3://aws-athena-query-results-533310886335-us-east-1'
            }
        )['QueryExecutionId']
        query_status = None
        while query_status == 'QUEUED' or query_status == 'RUNNING' or query_status is None:
            query_status = client.get_query_execution(QueryExecutionId=query_id)['QueryExecution']['Status']['State']
            if query_status == 'FAILED' or query_status == 'CANCELLED':
                raise Exception('Athena query with the string "{}" failed or was cancelled'.format(query_string))

            self.write(f'query_status: {query_status}')
            time.sleep(5)

        results_paginator = client.get_paginator('get_query_results')
        results_iter = results_paginator.paginate(
            QueryExecutionId=query_id,
            PaginationConfig={
                'PageSize': 1000
            }
        )
        results = []
        data_list = []
        columns = []

        for results_page in results_iter:
            columns = [
                col['Label']
                for col in results_page['ResultSet']['ResultSetMetadata']['ColumnInfo']
            ]

            for row in results_page['ResultSet']['Rows']:
                data_list.append(row['Data'])

        # names = [x['VarCharValue'] for x in data_list[0]]
        for datum in data_list[1:]:
            results.append([x['VarCharValue'] for x in datum])

        return [dict(zip(columns, x)) for x in results]

    def build_query(self, user):
        query = 'SELECT * FROM "shopifiedapplogs"."app_logs" WHERE ('
        query += '\n  OR '.join([f"strpos(message,'{ip}') > 0 " for ip in json.loads(user.profile.ips)])
        query += f''') AND '{user.date_joined:%Y-%m-%d}' <= dt
                AND strpos(message, '/api/all/orders-sync?since=') = 0
            ORDER BY generated_at'''

        self.write(f'Query:\n{query}\n')

        return query

    def generate_results(self, user):
        query = self.build_query(user)
        results = self.fetchall_athena(query)

        lines = ['\t'.join(["IP", "Time", "HTTP Method", "Path", "Status Code", "Response Bytes"])]
        for i in results:
            message = re.sub(r'hmac=[A-Za-z0-9]+', 'hmac=secret', i['message'])
            message = list(logfmt.parse(StringIO(message)))[0]
            date = arrow.get(i['generated_at']).datetime
            lines.append('\t'.join([
                message['fwd'].split(',')[0],
                f"{date:%d/%b/%Y:%H:%M:%S %z}",
                message['method'],
                f'"https://app.dropified.com{message["path"]}"',
                message['status'],
                message['bytes']
            ]))

        email_filename = re.sub(r"[@\.]", "_", user.email)

        url = aws_s3_upload(
            filename=f'activity/logs-{email_filename}.csv',
            content='\n'.join(lines),
            bucket_name='aws-athena-query-results-533310886335-us-east-1',
        )

        return url
