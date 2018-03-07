web: NEW_RELIC_CONFIG_FILE=app/config/newrelic_web.ini newrelic-admin run-program gunicorn app.wsgi --timeout 30 --limit-request-field_size 16380 --max-requests 10000 --max-requests-jitter 1000 --log-file -
worker: NEW_RELIC_CONFIG_FILE=app/config/celery_web.ini newrelic-admin run-program celery worker -A app -O fair -Q celery,priority_high
worker2: NEW_RELIC_CONFIG_FILE=app/config/celery_priority.ini newrelic-admin run-program celery worker -A app -O fair -Q priority_high
