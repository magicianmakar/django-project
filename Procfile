web: newrelic-admin run-program gunicorn app.wsgi --timeout 29 --log-file -
worker: newrelic-admin run-program celery worker --app=leadgalaxy.tasks.app
