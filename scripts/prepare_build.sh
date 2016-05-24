#!/bin/bash

export DATABASE_URL=postgres://postgres:@postgres:5432/python-test-app
export DEBUG_APP="TRUE"
export SENDGRID_PASSWORD=""
export SENDGRID_USERNAME=""
export S3_BUCKET_NAME='shopifiedapp'
export AWS_ACCESS_KEY_ID=''
export AWS_SECRET_ACCESS_KEY=''
export JVZOO_SECRET=''
export REDIS_URL="redis://127.0.0.1:6379"
export REDISCLOUD_URL="redis://127.0.0.1:6379"
export DEBUG_APP="TRUE"
export SENDGRID_PASSWORD=""
export SENDGRID_USERNAME=""
export S3_BUCKET_NAME='shopifiedapp'
export AWS_ACCESS_KEY_ID=''
export AWS_SECRET_ACCESS_KEY=''
export JVZOO_SECRET=''
export REDIS_URL="redis://127.0.0.1:6379"
export REDISCLOUD_URL="redis://127.0.0.1:6379"
export REDISCLOUD_CACHE="redis://127.0.0.1:6379"

#apt-get update -qy

apt-get install -y python-dev python-pip libmysqld-dev libssl-dev libffi-dev libxml2-dev libxslt1-dev

if [ ! -d "venv" ]; then
    virtualenv venv
fi
