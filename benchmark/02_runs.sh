#!/usr/bin/env bash
# All timed runs behind Figure 2 (Iceland 10 m, eight operations), one at a time, pinned to CPUS, in the final
# configuration of the published run. Resumable: a run that already has a row in runs.tsv is skipped (RESUME=0 to
# rerun everything). Run outside any sandbox, on a quiet machine, with Intel turbo off and the performance governor
# (run.sh needs host ps and the systemd user bus; see README.md).
# Usage: [STAGES="unlimited repeats rep3 longrep limits sedona"] [PLAN=1] ./02_runs.sh
#   unlimited  every package and GRASS configuration once under MemoryMax=$MEMMAX, operations in the order
#              fa cost relief resample slope algebra series focal (long ones last); within an operation GRASS goes
#              first and every other package is capped at cap_for(GRASS's fastest time) (rc 124 = time limit)
#   repeats    runs 2..REPS_SHORT of the short operations (relief resample slope algebra series), tags _r<n>
#   rep3       a third run of every pair of the short operations whose two times differ by more than REP3_SPREAD
#   longrep    a second run of the long runs in LONG_SAMPLE (checks that one run is enough), tags _r2
#   limits     the same runs under each of LIMIT_LEVELS (1G, dem = the DEM in memory): a run is tried when its
#              unlimited peak was <= 1.25 x the limit or it is a low-memory setting (GDAL 64 MB cache, terra todisk,
#              xarray-spatial on dask, r.terraflow memory=500); the others are skipped, with the reason in the log
#   sedona     Apache Sedona pipelines (GDAL tiles -> Sedona -> GDAL mosaic) on run_sb.sh (no cgroup; JVM peak)
# PLAN=1 prints the runs of the unlimited, repeats and limits stages without running anything.
set -u
cd "$(dirname "$0")"
. ./config.sh
[ -n "${PLAN:-}" ] || mkdir -p "$RESULTS" out/ops out/wbng out/tf_tmp
RESUME=${RESUME:-1}
P=$GRASS_PROJECT
SHORT="relief resample slope algebra series"
LONG="fa cost focal"
CORE="gdal terra saga wbw wbt xrs xrsdask tt richdem"  # packages of the main batch (limit levels: LIMIT_ALL=0)
T=$NTHREADS UNLIM_MEMMAX=$MEMMAX UNLIM_F64=$F64_MEMMAX
UNLIM=" $MEMMAX $F64_MEMMAX infinity "  # MemoryMax values of the unlimited runs (reference rows of the limit levels)

if [ -z "${PLAN:-}" ]; then
    for m in $GRASS_MAPSET $GRASS_OPS_MAPSET; do [ -d $P/$m ] || $GRASS_BIN -c -e $P/$m; done
    if [ "$REQUIRE_NO_TURBO" = 1 ] && [ -r /sys/devices/system/cpu/intel_pstate/no_turbo ] &&
        [ "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo)" != 1 ]; then
        echo "turbo is on (intel_pstate/no_turbo = 0): switch it off, or set REQUIRE_NO_TURBO=0" >&2; exit 1
    fi
fi

# ---------------------------------------------------------------- helpers
done_row() {  # done_row <name> [memmax]: "rc wall" of the last row of this run (rc=wait rows do not count)
    awk -F'\t' -v n="$1" -v m="${2:-}" '$2 == n && (m == "" || $4 == m) && $5 != "wait" {r = $5 " " $6} END {if (r != "") print r}' \
        "$RESULTS/runs.tsv" 2>/dev/null
}
ref_row() {  # ref_row <name>: "rc wall peak_GB" of the unlimited run (peak = cgroup for the MPI tool)
    awk -F'\t' -v n="$1" -v m="$UNLIM" '$2 == n && index(m, " " $4 " ") && $5 != "wait" {
        r = $5 " " $6 " " ((n ~ /^traudem/) ? $8 : $7)} END {if (r != "") print r}' "$RESULTS/runs.tsv" 2>/dev/null
}
last_wall() { awk -F'\t' 'END {if ($5 == "0") print $6}' "$RESULTS/runs.tsv"; }
fastest() { python3 -c "import sys; v = [float(x) for x in sys.argv[1:] if x]; print(min(v) if v else '')" "$@"; }
cap_for() {  # cap in seconds from GRASS's fastest time t: k t, k = 10 up to 0.5 h, 3 from 2 h on, log-linear between
    python3 -c "
import math, sys
t = float(sys.argv[1]); h = t / 3600
k = 10 if h <= 0.5 else 3 if h >= 2 else 10 * (h / 0.5) ** (math.log(0.3) / math.log(4))
print(int(max(k * t, float(sys.argv[2]))))" "$1" "$MIN_CAP_S"
}
rep_ok() {  # rep_ok <name without _r<n>>: whether this run is wanted in the current pass
    # longrep stage: only the long runs listed in LONG_SAMPLE
    [ -z "${SAMPLE:-}" ] || echo " $SAMPLE " | grep -q " $1 " || return 1
    [ "${REP:-}" = 3 ] || return 0
    # third run only where the first two finished and differ by more than REP3_SPREAD
    awk -F'\t' -v n="$1" -v m="$MEMMAX" -v k="$REP3_SPREAD" '$4 == m && $5 == "0" && ($2 == n || $2 == n "_r2") {t[$2] = $6}
        END {a = t[n]; b = t[n "_r2"]; exit !(a > 0 && b > 0 && (a > b ? a / b : b / a) > 1 + k)}' "$RESULTS/runs.tsv"
}
limit_ok() {  # limit_ok <name> <adaptive 0|1>: whether to try the run under LIMIT; records the reason when not
    local ref; ref=$(ref_row "$1")
    [ "$2" = 1 ] && return 0
    [ -z "$ref" ] && return 0
    set -- "$1" $ref
    if [ "$2" != 0 ]; then
        [ -n "${PLAN:-}" ] || printf "%s\t%s\t%sm\t%s\tunlimited rc %s\n" "$(date +%FT%T)" "$1" "$RES" "$LIMIT" "$2"; return 1
    fi
    if awk -v p="$4" -v b="$LIM_BYTES" 'BEGIN {exit !(p * 2^30 > 1.25 * b)}'; then
        [ -n "${PLAN:-}" ] || printf "%s\t%s\t%sm\t%s\tunlimited peak %s GB\n" "$(date +%FT%T)" "$1" "$RES" "$LIMIT" "$4"; return 1
    fi
}
ref_fits() {  # ref_fits <name>: the unlimited run finished with a peak <= 1.25 x the limit
    local ref; ref=$(ref_row "$1"); [ -n "$ref" ] || return 1
    set -- $ref
    [ "$1" = 0 ] && awk -v p="$3" -v b="$LIM_BYTES" 'BEGIN {exit !(p * 2^30 <= 1.25 * b)}'
}

grass() {  # grass <tag> <tool> [VAR=value...]: a GRASS run; keeps the operation's fastest GRASS time in GT
    local tag=$1 tool=$2 name d ref cap w; shift 2
    name=$tool${tag:+_$tag}
    if [ -n "${LIMIT:-}" ]; then
        ref=$(ref_row "$name")
        [ "$(echo "$ref" | cut -d' ' -f1)" = 0 ] && GT=$(fastest "$(echo "$ref" | cut -d' ' -f2)" "${GT:-}")
        limit_ok "$name" "${LIMONLY:-0}" || return
        cap=$([ -n "$ref" ] && python3 -c "print(int(max(3 * float('$(echo "$ref" | cut -d' ' -f2)'), $MIN_CAP_S)))" || echo 72000)
        [ -n "${PLAN:-}" ] && { printf "plan\t%s\t%s\tcap %s s\n" "$name" "$LIMIT" "$cap"; return; }
        [ "$RESUME" = 1 ] && [ -n "$(done_row "$name" "$MEMMAX")" ] && return
        env "$@" MEMMAX=$MEMMAX PIN=$CPUS RUN_TIMEOUT=$cap RUN_TAG=$tag taskset -c "$CPUS" ./run.sh "$RES" "$tool"
        return
    fi
    [ -n "${LIMONLY:-}" ] && return
    d=$(done_row "$name")  # the first run sets the cap of the others in every pass
    [ "${d%% *}" = 0 ] && GT=$(fastest "${d#* }" "${GT:-}")
    rep_ok "$name" || return
    name=$name${REP:+_r$REP}
    [ -n "${PLAN:-}" ] && { printf "plan\t%s\tunlimited\tGRASS\n" "$name"; return; }
    if [ "$RESUME" = 1 ] && d=$(done_row "$name") && [ -n "$d" ]; then
        [ "${d%% *}" = 0 ] && GT=$(fastest "${d#* }" "${GT:-}"); return
    fi
    env "$@" PIN=$CPUS RUN_TIMEOUT=${GRASS_CAP:-20h} RUN_TAG=$tag${REP:+_r$REP} taskset -c "$CPUS" ./run.sh "$RES" "$tool"
    w=$(last_wall)
    [ -n "$w" ] && GT=$(fastest "$w" "${GT:-}")
}
other() {  # other <tag> <tool> [VAR=value...]: a run of another package, capped at cap_for(GT)
    local tag=$1 tool=$2 name cap; shift 2
    name=$tool${tag:+_$tag}
    cap=$(cap_for "${GT:-$MIN_CAP_S}")
    if [ -n "${LIMIT:-}" ]; then
        limit_ok "$name" "${ADAPT:-0}" || return
        [ -n "${PLAN:-}" ] && { printf "plan\t%s\t%s\tcap %s s\n" "$name" "$LIMIT" "$cap"; return; }
        [ "$RESUME" = 1 ] && [ -n "$(done_row "$name" "$MEMMAX")" ] && return
        env "$@" MEMMAX=$MEMMAX PIN=$CPUS RUN_TIMEOUT=$cap RUN_TAG=$tag taskset -c "$CPUS" ./run.sh "$RES" "$tool"
        return
    fi
    [ -n "${LIMONLY:-}" ] && return
    rep_ok "$name" || return
    name=$name${REP:+_r$REP}
    [ -n "${PLAN:-}" ] && { printf "plan\t%s\tunlimited\tcap %s s\n" "$name" "$cap"; return; }
    [ "$RESUME" = 1 ] && [ -n "$(done_row "$name")" ] && return
    env MEMMAX=$MEMMAX "$@" PIN=$CPUS RUN_TIMEOUT=$cap RUN_TAG=$tag${REP:+_r$REP} taskset -c "$CPUS" ./run.sh "$RES" "$tool"
}
ops_others() {  # ops_others <op> <pkg>...: tools/ops_other.sh runs (series on the r.sun stack)
    local op=$1 p ss=; shift
    [ "$op" = series ] && ss=_sun
    for p in "$@"; do
        if [ -n "${LIMIT:-}" ] && [ "$LIMIT_ALL" != 1 ] && ! echo " $CORE " | grep -q " $p "; then continue; fi
        ADAPT=$([ "$p" = xrsdask ] && echo 1 || echo 0) other "$op${ss}_$p$([ "$op/$p" = relief/qgis ] && echo _v60)" ops_other \
            PKG=$p OP=$op ${ss:+SERIES_SET=sun}
    done
}
lowmem() {  # lowmem <op>: GDAL with a 64 MB cache and terra todisk, only under a limit the plain run does not fit
    local op=$1 ss=
    [ -n "${LIMIT:-}" ] || return
    [ "$op" = series ] && ss=_sun
    ref_fits ops_other_$op${ss}_gdal || LIMONLY=1 ADAPT=1 other $op${ss}_gdal_cache64 ops_other PKG=gdal OP=$op \
        GDAL_CACHEMAX=64 GDAL_WM=64 ${ss:+SERIES_SET=sun}
    ref_fits ops_other_$op${ss}_terra || LIMONLY=1 ADAPT=1 other $op${ss}_terra_todisk ops_other PKG=terra OP=$op \
        TERRA_TODISK=1 ${ss:+SERIES_SET=sun}
}
cand() {  # cand <op> <pkg>...: packages added after the main batch, same harness (no limit levels unless LIMIT_ALL=1)
    local op=$1 p ss=; shift
    [ -n "${LIMIT:-}" ] && [ "$LIMIT_ALL" != 1 ] && return
    [ "$op" = series ] && ss=_sun
    for p in "$@"; do other "$op${ss}_$p" ops_other PKG=$p OP=$op ${ss:+SERIES_SET=sun}; done
}

stage() {  # stage <op>: the runs of one operation
    GT=
    echo "== $1${REP:+ repeat $REP}${LIMIT:+ under $LIMIT} $(date +%FT%T)"
    case $1 in
        fa)
            grass sfd r.watershed RW_FLAGS="-s" RW_TAG=sfd
            grass m2400_sfd r.watershed RW_FLAGS="-m -s memory=2400" RW_TAG=m2400_sfd
            # r.terraflow memory=500, without and under a limit (more memory is not faster: memory=8000 2 %)
            grass terraflow_sfd_m500 grass \
                GCMD="r.terraflow -s elevation=elev_@R@m accumulation=tf_acc_sfd_@R@m memory=500 directory=$PWD/out/tf_tmp"
            other np$T traudem TAUDEM_NP=$T
            other d8_natural_t$T wbng WBNG_DEPS=natural WBNG_PROCS=$T
            other d8_t$T wbt WBT_PROCS=$T
            # Float64 tools known not to fit (RichDEM drove the host to 2 GB available, pysheds needs ~140 GB)
            other d8_f64_t$T richdem RICHDEM_DTYPE=float64 RICHDEM_THREADS=$T MEMMAX=$F64_MEMMAX
            other ms0.01 saga SAGA_MINSLOPE=0.01
            other d8_f64_eps pysheds PYSHEDS_DTYPE=float64 PYSHEDS_EPS=1e-9 MEMMAX=$F64_MEMMAX
            other d8 pyflwdir
            other d8 terra
            other d8 topotoolbox
            other d8 xrs
            if [ -z "${LIMIT:-}" ] || [ "$LIMIT_ALL" = 1 ]; then
                other landlab_d8 fa_cand PKG=landlab
                other pcraster_d8 fa_cand PKG=pcraster
            fi ;;
        cost)
            grass cost_grass_m300 ops_grass OP=cost COSTMEM=300
            grass cost_grass_m20000 ops_grass OP=cost COSTMEM=20000
            ops_others cost saga wbt wbw terra xrs
            cand cost rt skimage pcraster gdistance pyflwdir ;;
        relief)
            grass relief_grass ops_grass OP=relief
            ops_others relief gdal terra saga wbw wbt xrs xrsdask tt qgis; lowmem relief
            cand relief rt xdem xdemmp xdemmpw landlab geotools geotoolspar ;;
        resample)  # bicubic, 20 m onto the 10 m grid; r.resamp.interp with a small and a large cache
            grass resample_grass_m300_n$T ops_grass OP=resample RS_MEM=300 NP=$T
            grass resample_grass_m20000_n$T ops_grass OP=resample RS_MEM=20000 NP=$T
            ops_others resample gdal terra saga wbw wbt xrs xrsdask tt; lowmem resample
            cand resample rt xdem xdemmp xdemmpw skimage otb geotools geotools_c2g geotoolspar ;;
        slope)
            grass slope_grass_n$T ops_grass OP=slope NP=$T
            ops_others slope gdal terra saga wbw wbt xrs xrsdask tt richdem qgis; lowmem slope
            cand slope rt xdem xdemmp landlab pcraster pcrastermc ;;
        algebra)
            grass algebra_grass_n$T ops_grass OP=algebra NP=$T
            ops_others algebra gdal terra saga wbw wbt xrs xrsdask; lowmem algebra
            cand algebra rt xdem pcraster pcrastermc otb geotools ;;
        series)  # mean of the 12 r.sun layers (FCELL maps in GRASS, Float32 GeoTIFFs for the others)
            grass series_sun_grass_fcell ops_grass OP=series NP=$T SERIES_SET=sun
            ops_others series gdal terra saga wbw wbt xrs xrsdask qgis; lowmem series
            cand series rt xdem pcraster otb geotools ;;
        focal)
            grass focal_grass_n$T ops_grass OP=focal NP=$T
            ops_others focal gdal terra saga wbw wbt xrs xrsdask tt; lowmem focal
            cand focal rt xdem skimage geotools geotoolspar
            # Orfeo ToolBox: BandMathX's largest window, 21 x 21 (flag approximate)
            [ -n "${LIMIT:-}" ] && [ "$LIMIT_ALL" != 1 ] || other focal_otb ops_other PKG=otb OP=focal FOCAL_SIZE=21 ;;
    esac
}

info() {
    {
        echo "date $(date +%FT%T%z) res $RES rs_in $RS_IN focal $FOCAL_METHOD $FOCAL_SIZE memmax $MEMMAX" \
            "nthreads $NTHREADS cpus $CPUS xrs_chunk $XRS_CHUNK sig_digits $SIG_DIGITS min_cap_s $MIN_CAP_S"
        lscpu | grep -E '^(Model name|CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|CPU max MHz)'
        echo "memory_GB $(awk '/MemTotal/ {printf "%.0f", $2/1048576}' /proc/meminfo)"
        echo "kernel $(uname -r) governor $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)" \
            "no_turbo $(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)"
        echo "grass $($GRASS_BIN --version 2>/dev/null | head -1)"
        echo "affinity $(taskset -cp $$ | sed 's/.*: //') pinned_runs $CPUS" \
            "OMP_NUM_THREADS ${OMP_NUM_THREADS:-unset} NUMBA_NUM_THREADS ${NUMBA_NUM_THREADS:-unset}" \
            "RAYON_NUM_THREADS ${RAYON_NUM_THREADS:-unset} GDAL_NUM_THREADS ${GDAL_NUM_THREADS:-unset}"
        # WhiteboxTools stores the flags of its last call; every call here passes them (tools/ops_other.sh, wbt_flowacc.sh)
        echo "whitebox_tools_settings $(tr -d ' \n' <.venv/lib/python3.12/site-packages/whitebox/WBT/settings.json 2>/dev/null)"
    } >"$RESULTS/machine_$(date +%Y%m%dT%H%M).txt"
}

sedona() {  # Apache Sedona: tile (GDAL), write (Sedona), mosaic (GDAL), one run_sb.sh row per step
    local s=$SEDONA_RESULTS
    sb() {  # sb <op> <step> <tag> [VAR=value...]: one step; skipped when it has a finished row
        local op=$1 step=$2 tag=$3; shift 3
        [ "$RESUME" = 1 ] && awk -F'\t' -v n="sedona_$tag" '$2 == n && $5 == "0" {f = 1} END {exit !f}' "$s/runs.tsv" 2>/dev/null &&
            return 0
        env "$@" RESULTS=$s OP=$op SEDONA_STEP=$step RUN_TAG=$tag taskset -c "$CPUS" ./run_sb.sh "$RES" sedona
    }
    mkdir -p "$s"
    echo "== sedona $(date +%FT%T)"
    sb algebra tile algebra_tile && sb algebra write algebra_write_tiles SEDONA_INPUT=tiles RUN_TIMEOUT=1h &&
        sb algebra mosaic algebra_mosaic_tiles SEDONA_INPUT=tiles
    sb series tile series_tile_sun SERIES_SET=sun &&
        sb series write series_write_tiles_sun SERIES_SET=sun SEDONA_INPUT=tiles RUN_TIMEOUT=2h &&
        sb series mosaic series_mosaic_tiles_sun SERIES_SET=sun SEDONA_INPUT=tiles
    sb resample tile resample_tile_h2 HALO=2 && sb resample write resample_write_h2 HALO=2 SEDONA_INPUT=tiles RUN_TIMEOUT=1h &&
        sb resample mosaic resample_mosaic_h2 HALO=2 SEDONA_INPUT=tiles
}

[ -z "${PLAN:-}" ] && info
for st in ${STAGES:-unlimited repeats rep3 longrep limits sedona}; do
    echo "=== stage $st $(date +%FT%T)"
    case $st in
        unlimited) unset REP LIMIT; export MEMMAX=$UNLIM_MEMMAX F64_MEMMAX=$UNLIM_F64; for op in fa cost $SHORT focal; do stage $op; done ;;
        repeats) unset LIMIT
            for n in $(seq 2 "$REPS_SHORT"); do REP=$n; for op in $SHORT; do stage $op; done; done; unset REP ;;
        rep3) unset LIMIT; REP=3; for op in $SHORT; do stage $op; done; unset REP ;;
        longrep) unset LIMIT; REP=2; SAMPLE=$(eval echo "$LONG_SAMPLE")
            for op in fa cost focal; do stage $op; done; unset REP SAMPLE ;;
        limits) unset REP
            for LIMIT in $LIMIT_LEVELS; do
                case $LIMIT in
                    dem) LIM_BYTES=$(.venv-xrs/bin/python -c "import rasterio; s = rasterio.open('data/elev_${RES}m.tif'); print(s.width * s.height * 4)") ;;
                    *) LIM_BYTES=$(numfmt --from=iec "$LIMIT") ;;
                esac
                export MEMMAX=$LIM_BYTES F64_MEMMAX=$LIM_BYTES
                for op in fa cost $SHORT focal; do stage $op; done
            done
            unset LIMIT; export MEMMAX=$UNLIM_MEMMAX F64_MEMMAX=$UNLIM_F64 ;;
        sedona) [ -z "${PLAN:-}" ] && sedona ;;
        *) echo "unknown stage $st" >&2 ;;
    esac
done
echo "== done $(date +%FT%T)"
