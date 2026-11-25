#!/usr/bin/env bash
# Figure 2 from nothing: software, data, timed runs, agreement checks, figure. Each step can also be run on its own
# and the timed runs resume where they stopped (02_runs.sh). Settings: config.sh. See README.md before starting:
# the timed runs need a quiet machine with turbo off and take about five days.
# Usage: ./reproduce.sh [envs] [data] [runs] [checks] [figure]   (default: all, in this order)
set -eu
cd "$(dirname "$0")"
for s in ${@:-envs data runs checks figure}; do
    case $s in
        envs) ./00_envs.sh ;;
        data) ./01_data.sh ;;
        runs) ./02_runs.sh ;;
        checks) ./03_checks.sh ;;
        figure) ./04_figure.sh ;;
        *) echo "unknown step $s" >&2; exit 2 ;;
    esac
done
