#!/bin/bash

TYPE="$1"

if [ -z "$GUNICORN_TIMEOUT" ]; then
    GUNICORN_TIMEOUT="30"
fi

if [ "$TYPE" == "web" ]; then
    export NEW_RELIC_CONFIG_FILE="app/config/newrelic_web.ini"
    newrelic-admin run-program gunicorn app.wsgi --timeout $GUNICORN_TIMEOUT --limit-request-field_size 16380 --log-file -

elif [[ "$TYPE" == "worker" ]]; then
    export NEW_RELIC_CONFIG_FILE="app/config/celery_web.ini"
    export CELERY_STATEMENT_TIMEOUT="180000"

    newrelic-admin run-program celery worker -A app.celery_base -O fair -Q celery,priority_high

elif [[ "$TYPE" == "worker2" ]]; then
    export NEW_RELIC_CONFIG_FILE="app/config/celery_priority.ini"
    export CELERY_STATEMENT_TIMEOUT="180000"

    newrelic-admin run-program celery worker -A app.celery_base -O fair -Q priority_high

elif [[ "$TYPE" == "worker3" ]]; then
    python manage.py consume_alibaba_messages

else
    echo "[-] Can not run: $TYPE"
    exit 1
fi
