#!/usr/bin/env bash
# Usage: [MEMMAX=16G] [RUN_TAG=x] [RESULTS=dir] [GRASS_BIN=…] [ADDONS=dir] [GRASS_PROJECT=dir]
#        [MIN_AVAIL_GB=40] [MAX_WAIT_MIN=…] [RUN_TIMEOUT=…] run.sh <res> <tool>...   (tools: see tools/*.sh)
# MIN_AVAIL_GB: available memory the quiet-machine gate requires (set it above the tool's peak).
# MAX_WAIT_MIN: give up waiting after this many minutes and record the run as rc=wait (skipped).
# GATE_SEC: length of the quiet check (default 60 s; short values only for dry runs).
# RETRY_SEC: wait after a busy check before the next one (default 300 s).
# LOAD_MAX: 1-min load the quiet check accepts; default 4, or 12 when this run is pinned to 8 or fewer CPUs
# (other work on the remaining cores barely affects it).
# RUN_TIMEOUT: hard cap for the tool (timeout(1) syntax, e.g. 4h); a timed-out run has rc=124.
# Each tool run waits for a quiet machine (wait_idle), then runs in its own systemd user scope
# with MemoryMax=$MEMMAX (default: no limit) and no swap. Records the tool's own wall time and
# peak RSS (/usr/bin/time around the tool process, written by tools/<tool>.sh to $TIMEFILE) and
# the scope's cgroup memory.peak (includes page cache, so it is an upper bound).
# Must run outside any sandbox or container that hides host processes (needs host ps and the systemd user bus).
set -u
cd "$(dirname "$0")"
res=$1
shift
memmax=${MEMMAX:-infinity}
res_dir=${RESULTS:-results}
mkdir -p "$res_dir" out
tsv=$res_dir/runs.tsv
[ -s "$tsv" ] || printf "time\ttool\tres\tmemmax\trc\twall_s\tpeak_rss_GB\tcgroup_peak_GB\tload1\tmemavail_GB\tcpu_s\n" >"$tsv"
# cpu_s (user + sys) was added later; older rows lack it.
head -1 "$tsv" | grep -q cpu_s || sed -i '1s/$/\tcpu_s/' "$tsv"

ncpu=$(taskset -cp $$ | awk -F': ' '{n = 0; split($2, a, ","); for (i in a) {split(a[i], b, "-"); n += (b[2] == "" ? 1 : b[2] - b[1] + 1)}; print n}')
load_max=${LOAD_MAX:-$([ "$ncpu" -le 8 ] && echo 12 || echo 4)}

wait_idle() {
    # Quiet = over 60 s of 5 s samples: no r.viewshed/r.watershed processes from anyone,
    # 1-min load < 4, available memory > MIN_AVAIL_GB (default 40). Otherwise retry every 5 min,
    # until MAX_WAIT_MIN (if set): then return 1.
    local start=$(date +%s)
    while true; do
        local ok=1 i
        for i in $(seq $(( ${GATE_SEC:-60} / 5 ))); do
            if pgrep -x 'r\.viewshed|r\.watershed' >/dev/null ||
                pgrep -f '/etc/r\.watershed/(ram|seg)' >/dev/null ||
                awk -v m="$load_max" '{exit !($1 >= m)}' /proc/loadavg ||
                [ "$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)" -lt "${MIN_AVAIL_GB:-40}" ]; then
                ok=0
                break
            fi
            sleep 5
        done
        [ $ok = 1 ] && return
        echo "$(date +%T) busy: load $(cut -d' ' -f1 /proc/loadavg), available $(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo) GB; $(pgrep -ax 'r\.viewshed|r\.watershed' | head -1 | cut -c1-80)" >&2
        if [ -n "${MAX_WAIT_MIN:-}" ] && [ $(( ($(date +%s) - start) / 60 )) -ge "$MAX_WAIT_MIN" ]; then
            return 1
        fi
        sleep "${RETRY_SEC:-300}"
    done
}

for tool in "$@"; do
    name=$tool${RUN_TAG:+_$RUN_TAG}
    log=$res_dir/${name}_${res}m_mem${memmax}.log
    if ! wait_idle; then
        printf "%s\t%s\t%sm\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(date +%FT%T)" "$name" "$res" "$memmax" \
            wait NA 0.00 0.00 "$(cut -d' ' -f1 /proc/loadavg)" "$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)" NA | tee -a "$tsv"
        continue
    fi
    load=$(cut -d' ' -f1 /proc/loadavg)
    avail=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
    tf=$(mktemp)
    pf=$(mktemp)
    systemd-run --user --scope --quiet -p MemoryMax="$memmax" -p MemorySwapMax=0 \
        env TIMEFILE="$tf" bash -c '
            ${RUN_TIMEOUT:+timeout -k 60 $RUN_TIMEOUT} bash "tools/$1.sh" "$2"; rc=$?
            cat "/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)/memory.peak" >"$3"
            exit $rc' _ "$tool" "$res" "$pf" >"$log" 2>&1
    rc=$?
    read -r wall rss _ usr sys < <(tail -1 "$tf") || true
    rss_gb=$(awk -v k="${rss:-0}" 'BEGIN {printf "%.2f", k/1048576}')
    cpu=$(awk -v u="${usr:-}" -v s="${sys:-}" 'BEGIN {if (u == "") print "NA"; else printf "%.1f", u + s}')
    cg_gb=$(awk -v b="$(cat "$pf" 2>/dev/null || echo 0)" 'BEGIN {printf "%.2f", b/1073741824}')
    printf "%s\t%s\t%sm\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$(date +%FT%T)" "$name" "$res" "$memmax" \
        "$rc" "${wall:-NA}" "$rss_gb" "$cg_gb" "$load" "$avail" "$cpu" | tee -a "$tsv"
    rm -f "$tf" "$pf"
done
