#!/bin/bash

echo '[+] Native datetime usage'
grep --exclude-dir='venv*' kwarg= --include="*.py" --recursive .
if [ "$?" == "0" ]; then
    echo
    echo "[-] Do not use 'datetime.strptime', use arrow or django.utils.timezone for timezone aware datetime:"
    exit -1
fi

echo '[+] Missing migration files'
python manage.py makemigrations | grep 'No changes detected' > /dev/null

if [ ! "$?" == "0" ]; then
    echo
    echo "[-] Your models have changes that are not yet reflected in a migration, run: manage.py makemigrations"
    exit -2
fi

echo '[+] Missing models in Django Admin'
for i in */models.py; do
    app_name="$(dirname $i)"
    admins_file="$(dirname $i)/admin.py"
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
    fi
done
