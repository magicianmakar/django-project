web: NEW_RELIC_CONFIG_FILE=app/config/newrelic_web.ini newrelic-admin run-program gunicorn -c app/config/gunicorn.py app.wsgi --timeout 20 --log-file -
worker: NEW_RELIC_CONFIG_FILE=app/config/celery_web.ini newrelic-admin run-program celery worker -A leadgalaxy.tasks
