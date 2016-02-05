#!/bin/bash -e 

echo "* Start backup `date`"

cd /home/naruto/Desktop/shopify-app/backups

BACKUP_ID="`heroku pg:backups --app heroku-postgres-392cb678 | grep -E '[ab][0-9]+'|head -1| cut -d ' ' -f 1`"

if [ -z "$BACKUP_ID" ]; then
    echo "Couldn't get the backup ID"
    exit 1
fi

echo "* Last backup: $BACKUP_ID"
BACKUP_FILE="${BACKUP_ID}_`date +'%m-%d-%Y_pg.dump'`"
BACKUP_MARK="${BACKUP_ID}"

if [ -s "$BACKUP_MARK" ]; then
	echo "* File already exists: $BACKUP_MARK"
	exit 0
else
	echo "* Get download url for $BACKUP_ID"
	BACKUP_LINK=$(heroku pg:backups --app heroku-postgres-392cb678 public-url $BACKUP_ID|grep https|tr -d '"')
	#echo "* Link: $BACKUP_LINK"

    if [ -z "$BACKUP_LINK" ]; then
        echo "Couldn't get the backup Download Link"
        exit 2
    fi

	TEMP_FILE="`mktemp`"
	cat << EOF > $TEMP_FILE
cd /root/backups/shopifiedapp/database
echo -n "* Current dir: "
pwd

if [ -s "$BACKUP_FILE" ]; then
	echo "* File already exists: $BACKUP_FILE"
	exit 0
else
	echo "* Downloading backup $BACKUP_ID"
	wget '$BACKUP_LINK' -O $BACKUP_FILE

    curl --progress-bar -u justroftest@gmail.com:05A2970151F -T "$BACKUP_FILE"  "https://dav.box.com/dav/backups/";
fi

EOF

	echo "* Upload Temp file: $TEMP_FILE"
	scp -P 8465 -C $TEMP_FILE root@162.243.76.139:/tmp/backupcmd.sh
	
	echo "* Execute backup script on remote"
	ssh -p 8465 root@162.243.76.139 "nohup bash /tmp/backupcmd.sh >/root/backups/shopifiedapp/database/backup.log 2>&1 &"

	rm -f $TEMP_FILE
	
	date > $BACKUP_MARK
fi
