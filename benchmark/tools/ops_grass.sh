#!/usr/bin/env bash
# One raster operation in GRASS: tools/ops_grass.sh <res>, called by run.sh. OP = relief | slope | focal
# (FOCAL_METHOD, FOCAL_SIZE) | cost (r.cost + r.path, COSTMEM, COST_START, COST_END) | algebra (ops_expr.py) | resample
# (r.resamp.interp from elev_<RS_IN>m, RS_MEM) | series (r.series of ser<SERIES_SET><k>_<res>m, k = 1..12); NP = nprocs
# (default 1); GMEM = memory= of r.slope.aspect, r.neighbors and r.series (unset: the tool's default); PIN = CPU list for
# taskset ("all" = no pinning). Inputs in PERMANENT of GRASS_PROJECT, outputs in mapset GRASS_OPS_MAPSET (default ops).
# /usr/bin/time wraps the tool processes inside the session (no import or export).
cd "$(dirname "$0")/.."
G=${GRASS_BIN:-$PWD/grass-85-o2/bin.x86_64-pc-linux-gnu/grass}
r=$1 e=elev_$1m np=${NP:-1}
case $OP in
    relief) c="r.relief input=$e output=rel --o" ;;
    slope) c="r.slope.aspect elevation=$e slope=slp aspect=asp nprocs=$np ${GMEM:+memory=$GMEM} --o" ;;
    focal) c="r.neighbors input=$e output=avg size=${FOCAL_SIZE:-5} method=$([ "${FOCAL_METHOD:-mean}" = median ] && echo median || echo average) nprocs=$np ${GMEM:+memory=$GMEM} --o" ;;
    algebra) mkdir -p out/ops && echo "alg = $(python3 ops_expr.py grass $e)" > out/ops/algebra_${r}m.mapcalc
             c="r.mapcalc file=$PWD/out/ops/algebra_${r}m.mapcalc nprocs=$np --o" ;;
    resample) c="r.resamp.interp input=elev_${RS_IN:-3}m output=rs method=${RS_METHOD:-bicubic} memory=${RS_MEM:-300} nprocs=$np --o" ;;  # onto the <res> grid
    series) c="r.series input=$(for k in $(seq 12); do printf "ser${SERIES_SET}%d_%sm@PERMANENT," $k $r; done | sed 's/,$//') output=smean method=average nprocs=$np ${GMEM:+memory=$GMEM} --o" ;;
    cost) c="r.cost input=friction_${r}m output=cost outdir=cdir start_coordinates=${COST_START:-1122385,-2618715} memory=${COSTMEM:-300} --o && r.path input=cdir format=auto start_coordinates=${COST_END:-1206305,-2388085} raster_path=lcp --o" ;;
    *) echo "unknown OP=$OP" >&2; exit 2 ;;
esac
[ "${PIN:-0-15}" = all ] && pin= || pin="taskset -c ${PIN:-0-15}"
P=${GRASS_PROJECT:-project}  # project_iceland for Iceland (paper_iceland.sh)
M=${GRASS_OPS_MAPSET:-ops}
[ -d $P/$M ] || $G -c -e $P/$M
$pin $G $P/$M --exec bash -c "g.region raster=$e && /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE bash -c '$c'"
