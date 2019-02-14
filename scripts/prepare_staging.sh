#!/bin/bash

echo "Load application fixtures..."

./manage.py loaddata app/data/fixtures/staging.json
