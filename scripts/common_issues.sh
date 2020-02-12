#!/bin/bash

grep datetime.strptime --exclude-dir='venv*' --include="*.py" --recursive .
if [ "$?" == "0" ]; then
    echo
    echo "[-] Do not use 'datetime.strptime', use arrow or django.utils.timezone for timezone aware datetime:"
    exit -1
fi

grep 'kwarg=' --exclude-dir='venv*' --include="*.py" --recursive .
if [ "$?" == "0" ]; then
    echo
    echo "[-] kwarg= seem to be a typo, do you mean kwargs?"
    exit -1
fi

grep django.contrib.postgres --exclude-dir='venv*' --include="*.py" --exclude-dir="phone_automation" --recursive .
if [ "$?" == "0" ]; then
    echo
    echo "[-] Do not use 'django.contrib.postgres' unless necessary"
    exit -1
fi

grep pdb --exclude-dir='venv*' --include="*.py" --recursive .
if [ "$?" == "0" ]; then
    echo
    echo "[-] pdb detected, forgotten debugging line?"
    exit -1
fi

grep -E "{% static ['\"]/[^'\"]+['\"] %}" --exclude-dir='venv*' --include="*.html" --recursive .
if [ "$?" == "0" ]; then
    echo
    echo "[-] static tag argument should not start with a slash"
    exit -1
fi

OUTFILE="$(mktemp)"
python manage.py makemigrations > $OUTFILE 2>&1
grep 'No changes detected' $OUTFILE > /dev/null

if [ ! "$?" == "0" ]; then
    echo
    echo "[-] Your models have changes that are not yet reflected in a migration:"
    cat $OUTFILE
    exit -2
fi

DJANGO_ADMIN_ERROR=""
for i in */models.py; do
    app_name="$(dirname $i)"
    admins_file="$(dirname $i)/admin.py"

    if [ "$app_name" == "shopified_core" ]; then
        continue
    fi

    if [ ! -f $admins_file ]; then
        echo "[-] Admin file is missing: $admins_file"
        echo "    Generate with:"
        echo "    ./manage.py admin_generator -r 0 $app_name >> $admins_file"
        echo

        #./manage.py admin_generator -r 0 $app_name >> $admins_file
        continue
    fi

    missing=""
    for c in $(grep models.Model $i | grep -E 'class (+[^(]+)\(' -o | cut -d ' ' -f 2 | tr -d '('); do

        if [ "$c" == "FeedStatusAbstract" ]; then
            continue
        fi

        if [ "$c" == "AddressBase" ]; then
            continue
        fi

        if [ "$c" == "AbstractImage" ]; then
            continue
        fi

        if [ "$c" == "AbstractOrderInfo" ]; then
            continue
        fi

        if [ "$c" == "AbstractPayout" ]; then
            continue
        fi

        grep "$c" "$admins_file" > /dev/null

        if [ "$?" != "0" ]; then
            #echo "    Generate with: ./manage.py admin_generator -r 0 $app_name $c"
            missing="$missing$c "
            echo
        fi
    done

    if [ -n "$missing" ]; then
        echo "[-] Following models not found in $admins_file:"
        for c in $(echo $missing | tr -t ' ' '\n'); do
            echo "    $c"
        done

        echo
        echo "    Generate with:"
        echo "    ./manage.py admin_generator -r 0 $app_name $missing >> $admins_file"
        echo

        DJANGO_ADMIN_ERROR="1"
    fi
done

if [ -n "$DJANGO_ADMIN_ERROR" ]; then
    exit -2
fi

if [ -n "$CIRCLE_BRANCH" ]; then
    echo "INSTALLED_APPS += ('django_template_check',)" >> app/settings.py
fi
