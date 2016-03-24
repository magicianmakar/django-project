web: newrelic-admin run-program gunicorn app.wsgi --timeout 29 --log-file -
worker: NEW_RELIC_APP_NAME="ShopifiedApp (Celery)" newrelic-admin run-program celery worker --app=leadgalaxy.tasks.app
