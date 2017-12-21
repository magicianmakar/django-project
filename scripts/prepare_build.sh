#!/bin/bash

if [ -z "$DATABASE_URL" ]; then
    export DATABASE_URL="postgres://postgres:@postgres:5432/default-db"
fi

if [ -z "$DATA_STORE_DATABASE_URL" ]; then
    export DATA_STORE_DATABASE_URL="postgres://postgres:@postgres:5432/store-db"
fi

if [ -z "$REDISCLOUD_URL" ]; then
    export REDISCLOUD_URL="redis://${REDIS_PORT_6379_TCP_ADDR}:${REDIS_PORT_6379_TCP_PORT}"
fi

export REDISCLOUD_CACHE="$REDISCLOUD_URL"

export DEBUG_APP="TRUE"
export SENDGRID_PASSWORD=""
export SENDGRID_USERNAME=""
export S3_BUCKET_NAME='shopifiedapp-assets'
export AWS_ACCESS_KEY_ID=""
export AWS_SECRET_ACCESS_KEY=""
export JVZOO_SECRET=""
export STRIPE_PUBLIC_KEY=""
export STRIPE_SECRET_KEY=""
export SHOPIFY_API_KEY=""
export SHOPIFY_API_SECRET=""


if [ ! -d "venv" ]; then
    virtualenv venv
fi

sudo pip install -U pip
sudo pip install flake8
