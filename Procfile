web: newrelic-admin run-program gunicorn -c app/config/gunicorn.py app.wsgi --timeout 20 --log-file -
worker: NEW_RELIC_APP_NAME="ShopifiedApp (Celery)" newrelic-admin run-program celery worker -A leadgalaxy.tasks
