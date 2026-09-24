#!/usr/bin/env bash
# Start Mealplanner. Gebruikt de Python-omgeving in .venv (met het anthropic-pakket) als die er is.
# Extra opties worden doorgegeven, bijvoorbeeld: ./start.sh --port 8080
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m mealplanner.server "$@"
else
  echo "Let op: geen .venv gevonden; de functies met Claude werken dan niet (zie README)." >&2
  exec python3 -m mealplanner.server "$@"
fi
