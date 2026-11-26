#!/usr/bin/env bash
# Figure 2 and its numbers from runs.tsv (no hand-typed values):
#   paper_data.py  selection rule per package and operation -> out/figure2/paper_points.csv (one row per point, with
#                  the ratios and the reasons of runs that did not finish) and out/figure2/paper_numbers.csv (the
#                  numbers the paper cites), copied to $RESULTS/paper_numbers.csv
#   make_p1.py     Figure 2 -> $RESULTS/figures/figure-benchmark.png
# Usage: ./04_figure.sh
set -eu
cd "$(dirname "$0")"
. ./config.sh
PY=$PWD/.venv-xrs/bin/python
export MPLCONFIGDIR=$PWD/out/.mpl
$PY paper_data.py "$RESULTS" ice10 out/figure2
cp out/figure2/paper_numbers.csv "$RESULTS/"
$PY make_p1.py out/figure2 "$RESULTS/figures"
