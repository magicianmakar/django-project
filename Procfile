web: NEW_RELIC_CONFIG_FILE=app/config/newrelic_web.ini newrelic-admin run-program gunicorn app.wsgi --timeout 30 --log-file -
worker: NEW_RELIC_CONFIG_FILE=app/config/celery_web.ini newrelic-admin run-program celery worker -A app -O fair -Q celery,priority_high
worker2: NEW_RELIC_CONFIG_FILE=app/config/celery_priority.ini newrelic-admin run-program celery worker -A app -O fair -Q priority_high
