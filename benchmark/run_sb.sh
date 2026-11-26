#!/usr/bin/env bash
# The harness of the Apache Sedona steps (tools/sedona.sh): the same runs.tsv columns as run.sh, without a systemd
# scope. The quiet-machine gate checks the 1-min load, the available memory and that the CPUs this run is pinned to
# were < 10 % busy over GATE_SEC. Peak memory: the JVM's peak RSS (VmHWM) plus the Python driver's peak, written by
# sedona_ops.py to $PEAKFILE (cgroup_peak_GB column; /usr/bin/time's peak RSS in peak_rss_GB), the same quantity
# as the peak RSS of the other packages summed over the two processes. memmax holds the JVM heap (SEDONA_HEAP),
# cpu_s includes the JVM's CPU time. There is no MemoryMax, so Sedona has no memory-limit runs.
# Usage: [RESULTS=dir] [RUN_TAG=x] [RUN_TIMEOUT=…] [GATE_SEC=60] [MAX_WAIT_MIN=…] run_sb.sh <res> <tool>...
set -u
cd "$(dirname "$0")"
res=$1
shift
res_dir=${RESULTS:-results_sedona}
mkdir -p "$res_dir"
tsv=$res_dir/runs.tsv
[ -s "$tsv" ] || printf "time\ttool\tres\tmemmax\trc\twall_s\tpeak_rss_GB\tcgroup_peak_GB\tload1\tmemavail_GB\tcpu_s\n" >"$tsv"
cpus=$(taskset -cp $$ | awk -F': ' '{print $2}')
ncpu=$(echo "$cpus" | awk '{n = 0; split($1, a, ","); for (i in a) {split(a[i], b, "-"); n += (b[2] == "" ? 1 : b[2] - b[1] + 1)}; print n}')
load_max=${LOAD_MAX:-$([ "$ncpu" -le 8 ] && echo 12 || echo 4)}
busy_pct() {  # busy % of the pinned CPUs over $1 seconds
    local f=$(mktemp) g=$(mktemp)
    awk '/^cpu[0-9]/' /proc/stat > $f; sleep $1; awk '/^cpu[0-9]/' /proc/stat > $g
    paste $f $g | awk -v set="$cpus" 'BEGIN {n = split(set, a, ","); for (i = 1; i <= n; i++) {m = split(a[i], b, "-"); for (c = b[1]; c <= (m > 1 ? b[2] : b[1]); c++) want["cpu" c] = 1}}
        want[$1] {b0 = $2 + $3 + $4 + $7 + $8; i0 = $5 + $6; o = NF / 2; b1 = $(o+2) + $(o+3) + $(o+4) + $(o+7) + $(o+8); i1 = $(o+5) + $(o+6); B += b1 - b0; I += i1 - i0}
        END {printf "%d", 100 * B / (B + I + 0.001)}'
    rm -f $f $g
}
wait_idle() {
    local start=$(date +%s)
    while true; do
        local b=$(busy_pct ${GATE_SEC:-60})
        if [ "$b" -lt 10 ] && awk -v m="$load_max" '{exit ($1 >= m)}' /proc/loadavg &&
            [ "$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)" -ge "${MIN_AVAIL_GB:-40}" ]; then
            return 0
        fi
        echo "$(date +%T) busy: pinned CPUs $b %, load $(cut -d' ' -f1 /proc/loadavg)" >&2
        if [ -n "${MAX_WAIT_MIN:-}" ] && [ $(( ($(date +%s) - start) / 60 )) -ge "$MAX_WAIT_MIN" ]; then return 1; fi
        sleep "${RETRY_SEC:-300}"
    done
}
for tool in "$@"; do
    name=$tool${RUN_TAG:+_$RUN_TAG}
    log=$res_dir/${name}_${res}m.log
    if ! wait_idle; then
        printf "%s\t%s\t%sm\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(date +%FT%T)" "$name" "$res" "${SEDONA_HEAP:-48g}" wait NA 0.00 NA \
            "$(cut -d' ' -f1 /proc/loadavg)" "$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)" NA | tee -a "$tsv"
        continue
    fi
    load=$(cut -d' ' -f1 /proc/loadavg) avail=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
    tf=$(mktemp) pf=$(mktemp)
    TIMEFILE=$tf PEAKFILE=$pf ${RUN_TIMEOUT:+timeout -k 60 $RUN_TIMEOUT} bash tools/$tool.sh $res >"$log" 2>&1
    rc=$?
    read -r wall rss _ usr sys < <(tail -1 "$tf") || true
    read -r jvm py jcpu < "$pf" 2>/dev/null || true
    rss_gb=$(awk -v k="${rss:-0}" 'BEGIN {printf "%.2f", k/1048576}')
    sum_gb=$(awk -v j="${jvm:-}" -v p="${py:-0}" 'BEGIN {if (j == "" || j < 0) print "NA"; else printf "%.2f", (j + p)/1048576}')
    cpu=$(awk -v u="${usr:-}" -v s="${sys:-}" -v j="${jcpu:-0}" 'BEGIN {if (u == "") print "NA"; else printf "%.1f", u + s + j}')
    printf "%s\t%s\t%sm\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(date +%FT%T)" "$name" "$res" "${SEDONA_HEAP:-48g}" \
        "$rc" "${wall:-NA}" "$rss_gb" "$sum_gb" "$load" "$avail" "$cpu" | tee -a "$tsv"
    rm -f "$tf" "$pf"
done
exit "$rc"  # the last run's status, so callers can chain on success (a capped run is 124)
