#!/usr/bin/env bash
cd "$(dirname "$0")/.."
OPENBLAS_NUM_THREADS=1 /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE .venv/bin/python pyflwdir_flowacc.py data/elev_${1}m.tif out/acc_pyflwdir_${1}m.tif
