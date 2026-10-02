#!/bin/bash
cd "$(dirname "$0")/backend"
if [ -f venv/Scripts/activate ]; then source venv/Scripts/activate; else source venv/bin/activate; fi
python app.py
