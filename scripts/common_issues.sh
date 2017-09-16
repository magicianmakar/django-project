#!/bin/bash

grep --exclude-dir=venv datetime.strptime --include="*.py" --recursive .

if [ "$?" == "0" ]; then
    echo
    echo "[-] Do not use 'datetime.strptime', use arrow or django.utils.timezone for timezone aware datetime:"
    exit -1
fi

python manage.py makemigrations | grep 'No changes detected'

if [ ! "$?" == "0" ]; then
    echo
    echo "[-] Your models have changes that are not yet reflected in a migration, run: manage.py makemigrations"
    exit -2
fi
