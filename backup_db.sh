#!/bin/bash -e 

echo "* Start backup `date`"

cd /home/naruto/Desktop/shopify-app/backups

BACKUP_ID="`heroku pg:backups --app heroku-postgres-392cb678 | grep -E '[ab][0-9]+'|head -1| cut -d ' ' -f 1`"

echo "* Last backup: $BACKUP_ID"
BACKUP_FILE="${BACKUP_ID}_`date +'%m-%d-%Y_pg.dump'`"
if [ -s "$BACKUP_FILE" ]; then
	echo "* File already exists: $BACKUP_FILE"
	exit 0
else
	echo "* Get download url for $BACKUP_ID"
	BACKUP_LINK=$(heroku pg:backups --app heroku-postgres-392cb678 public-url $BACKUP_ID|grep https|tr -d '"')
	#echo "* Link: $BACKUP_LINK"

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
fi

EOF

	echo "* Upload Temp file: $TEMP_FILE"
	scp -P 8465 -C $TEMP_FILE root@162.243.76.139:/tmp/backupcmd.sh
	
	echo "* Execute backup script on remote"
	ssh -p 8465 root@162.243.76.139 "bash /tmp/backupcmd.sh"

	rm -f $TEMP_FILE
	
	date > $BACKUP_FILE
fi
