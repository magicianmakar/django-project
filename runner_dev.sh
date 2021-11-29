#!/bin/bash

TYPE="$1"

source venv/bin/activate

if [ "$TYPE" == "web" ]; then
    python manage.py runserver

elif [[ "$TYPE" == "worker" ]]; then
    celery -A app.celery_base worker -Q celery,priority_high -O fair -l INFO

elif [[ "$TYPE" == "worker2" ]]; then
    celery -A app.celery_base worker -Q celery -O fair -l INFO

elif [[ "$TYPE" == "worker3" ]]; then
    python manage.py consume_alibaba_messages

else
    echo "[-] Can not run: $TYPE"
    exit 1
fi
