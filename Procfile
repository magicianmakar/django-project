web: NEW_RELIC_CONFIG_FILE=app/config/newrelic_web.ini newrelic-admin run-program gunicorn app.wsgi --timeout 30 --limit-request-field_size 16380 --log-file -
worker: CELERY_STATEMENT_TIMEOUT=180000 NEW_RELIC_CONFIG_FILE=app/config/celery_web.ini newrelic-admin run-program celery worker -A app.celery_base -O fair -Q celery,priority_high
worker2: CELERY_STATEMENT_TIMEOUT=180000 NEW_RELIC_CONFIG_FILE=app/config/celery_priority.ini newrelic-admin run-program celery worker -A app.celery_base -O fair -Q priority_high
worker3: python manage.py consume_alibaba_messages
