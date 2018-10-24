#!/bin/bash

if [ ! -d "venv" ]; then
    virtualenv venv
fi

sudo pip install pip flake8==3.5.0

