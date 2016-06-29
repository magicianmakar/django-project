#!/bin/bash

export DATABASE_URL="postgres://postgres:@postgres:5432/python-test-app"
export DEBUG_APP="TRUE"
export SENDGRID_PASSWORD=""
export SENDGRID_USERNAME=""
export S3_BUCKET_NAME='shopifiedapp'
export AWS_ACCESS_KEY_ID=""
export AWS_SECRET_ACCESS_KEY=""
export JVZOO_SECRET=""
export REDISCLOUD_URL="redis://${REDIS_PORT_6379_TCP_ADDR}:${REDIS_PORT_6379_TCP_PORT}"
export REDISCLOUD_CACHE="redis://${REDIS_PORT_6379_TCP_ADDR}:${REDIS_PORT_6379_TCP_PORT}"
export STRIPE_PUBLIC_KEY=""
export STRIPE_SECRET_KEY=""

apt-get update -qy

apt-get install -y python-dev python-pip libmysqld-dev libssl-dev libffi-dev libxml2-dev libxslt1-dev

if [ ! -d "venv" ]; then
    virtualenv venv
fi
