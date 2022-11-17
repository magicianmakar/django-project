#!/bin/bash

if [ ! -d "venv" ]; then
    virtualenv --python python3.8 venv
fi
