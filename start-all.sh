#!/bin/bash
cd "$(dirname "$0")"
trap 'kill 0' EXIT
./start-backend.sh &
./start-frontend.sh &
wait
