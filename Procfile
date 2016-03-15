web: newrelic-admin run-program gunicorn app.wsgi --timeout 29 --log-file -
worker: celery worker --app=leadgalaxy.tasks.app
