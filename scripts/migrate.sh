#!/bin/bash

source venv/bin/activate
source scripts/env.sh

python manage.py migrate
python manage.py migrate --database store_db