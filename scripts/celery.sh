#!/bin/bash

source venv/bin/activate
source scripts/env.sh

celery -A leadgalaxy.tasks worker -Q celery,priority_high -O fair -l INFO
