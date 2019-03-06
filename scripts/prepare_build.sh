#!/bin/bash

if [ ! -d "venv" ]; then
    virtualenv venv
fi

sudo pip install pip configparser==3.5.0 flake8==3.7.7

