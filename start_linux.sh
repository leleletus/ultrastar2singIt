#!/bin/bash
# Opens the converter from the project folder, with its venv when there is one (python3 of the system otherwise).
cd "$(dirname "$0")"
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
    exec python LetsSingUltraStarConverter.py "$@"
fi
exec python3 LetsSingUltraStarConverter.py "$@"
