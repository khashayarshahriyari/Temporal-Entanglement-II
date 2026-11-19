#!/usr/bin/env bash
# bash run.sh                 collect fresh events, then open the map
# bash run.sh update [opts]   only collect (e.g. --only slso,cam   --days 21   --no-browser)
# bash run.sh serve           only open the map with the events you already have
# bash run.sh diagnose <id>   show what the scraper sees for one venue (e.g. new-music-circle)
cd "$(dirname "$0")"
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
case "${1:-}" in
  "")     $PY update.py && exec $PY serve.py ;;
  update) shift; exec $PY update.py "$@" ;;
  serve)  shift; exec $PY serve.py "$@" ;;
  diagnose) shift; exec $PY diagnose.py "$@" ;;
  *)      echo "usage: bash run.sh [update|serve|diagnose] [options]"; exit 2 ;;
esac
