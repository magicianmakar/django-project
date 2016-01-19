#!/bin/bash -e

git push heroku master
heroku run python manage.py migrate

