# Settings of the benchmark, sourced by 00_envs.sh .. 04_figure.sh. Every value can be overridden from the
# environment (e.g. CPUS=0-15 NTHREADS=16 ./02_runs.sh). The values below are the ones of the published run.

# machine
export CPUS=${CPUS:-0-7}            # CPU list every timed run is pinned to (taskset)
export NTHREADS=${NTHREADS:-8}      # threads or processes of every multi-threaded tool (same number as CPUS)
export MEMMAX=${MEMMAX:-110G}       # cgroup MemoryMax of an unlimited run (no swap); the reference machine had 125 GB
export F64_MEMMAX=${F64_MEMMAX:-100G}  # RichDEM and pysheds in Float64: known not to fit, capped lower to protect the host
export HOST_GB=${HOST_GB:-125}      # RAM of the machine (paper_data.py: the limit of a run without MemoryMax)
export MIN_CAP_S=${MIN_CAP_S:-3600} # shortest time limit of a run of another package (s)
# quiet-machine gate of run.sh before every run
export MIN_AVAIL_GB=${MIN_AVAIL_GB:-30} MAX_WAIT_MIN=${MAX_WAIT_MIN:-240} RETRY_SEC=${RETRY_SEC:-60}
export REQUIRE_NO_TURBO=${REQUIRE_NO_TURBO:-1}  # 02_runs.sh stops when Intel turbo is on (intel_pstate/no_turbo != 1)

# where things go (relative to this directory)
export RESULTS=${RESULTS:-results_iceland}        # runs.tsv of run.sh, paper_points.csv, figures/
export SEDONA_RESULTS=${SEDONA_RESULTS:-$RESULTS/sedona}  # runs.tsv of run_sb.sh (Apache Sedona steps)

# benchmark settings (the decisions behind Figure 2; see README.md and figure2.ipynb)
export RES=ice10 RS_IN=ice20       # Iceland 10 m DEM; resampling from the 20 m DEM onto the 10 m grid
export FOCAL_METHOD=median FOCAL_SIZE=25
export XRS_CHUNK=1024              # dask chunk size (cells per side) of xarray-spatial on dask and resampling
export SIG_DIGITS=4                # Whitebox median filters: values binned to 4 decimals (0.1 mm)
export COST_SITE=ice COST_START=1122385,-2618715 COST_END=1206305,-2388085  # Reykjavik -> Akureyri, EPSG:3413
export GRASS_PROJECT=project_iceland GRASS_MAPSET=tier1 GRASS_OPS_MAPSET=ops
export GRASS_BIN=${GRASS_BIN:-$PWD/grass-85-o2/bin.x86_64-pc-linux-gnu/grass}
export SEDONA_HEAP=${SEDONA_HEAP:-100g}

# repeats: the short operations (relief, resampling, slope, algebra, series) run REPS_SHORT times, the long ones
# (flow accumulation, least-cost path, focal median) once; a pair of runs that differs by more than REP3_SPREAD gets
# a third run. Time = median over the runs.
export REPS_SHORT=${REPS_SHORT:-2} REP3_SPREAD=${REP3_SPREAD:-0.05}
# long runs repeated once as a sample (stage longrep; the published points use these second runs). $T = NTHREADS
export LONG_SAMPLE=${LONG_SAMPLE:-'r.watershed_sfd r.watershed_m2400_sfd grass_terraflow_sfd_m500 ops_grass_cost_grass_m300 ops_grass_focal_grass_n$T ops_other_focal_gdal wbt_d8_t$T pyflwdir_d8'}
# memory-limit levels after the unlimited runs (1G and the DEM size in memory, 8.0 GiB)
export LIMIT_LEVELS=${LIMIT_LEVELS:-1G dem}
# 0: the limit levels cover the packages of the main batch, as in the published run; 1: also the packages added
# later (raster_tools, xDEM, scikit-image, Landlab, PCRaster, gdistance, Orfeo ToolBox, GeoTools, pyflwdir, QGIS)
export LIMIT_ALL=${LIMIT_ALL:-0}
