#!/bin/bash

if [ ! -d "venv" ]; then
    virtualenv venv
fi

sudo pip install -U pip
sudo pip install flake8
