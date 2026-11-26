#!/usr/bin/env bash
# One raster operation in a package other than GRASS: tools/ops_other.sh <res>, called by run.sh.
# PKG = gdal | terra | saga | wbw | wbt | xrs | xrsdask | tt | richdem | qgis (ops_py.py, resample_py.py for the Python
# ones) | rt | xdem | xdemmp | xdemmpw | skimage | landlab | pcraster | pcrastermc | pyflwdir (ops_cand.py) | gdistance (cost_gdistance.R) | otb |
# geotools | geotools_c2g | geotoolspar (geotools/Ops.java); OP as in tools/ops_grass.sh. TERRA_TODISK=1, GDAL_CACHEMAX /
# GDAL_WM: settings that only trade memory. PIN = CPU list for taskset ("all" = no pinning). Input GeoTIFF
# data/elev_<res>m.tif (resampling: data/elev_<RS_IN>m.tif; series: data/series/<res>m_<SERIES_SET>/s<k>.tif;
# cost: data/cost/), output out/ops/<op>[_<SERIES_SET>]_<pkg>_<res>m.tif.
cd "$(dirname "$0")/.."
r=$1 C=data/cost d=data/elev_$1m.tif o=out/ops/${OP}${SERIES_SET:+_$SERIES_SET}_${PKG}_$1m
R=$PWD/mamba/root/envs/r S=$PWD/saga/root/usr Q=$PWD/mamba/root/envs/qgis
WBT=$PWD/.venv/lib/python3.12/site-packages/whitebox/WBT/whitebox_tools
# WhiteboxTools keeps max_procs, compress_rasters and working_directory in WBT/settings.json and a call without
# the flags uses the stored values: set them on every call
WBTF="--max_procs=${NTHREADS:-16} --compress_rasters=true --wd=$PWD/"
export GDAL_NUM_THREADS=${NTHREADS:-16} MPLCONFIGDIR=$PWD/out/ops/.mpl
export SAGA_TLB=$S/lib/x86_64-linux-gnu/saga SAGA_SHARE=$S/share/saga LD_LIBRARY_PATH=$S/lib/x86_64-linux-gnu
pre="suppressMessages(library(terra)); terraOptions(threads = ${NTHREADS:-16}, parallel = TRUE); ${TERRA_TODISK:+terraOptions(todisk = TRUE, memmax = 0.5);} r <- rast('$d');"  # TERRA_TODISK=1: process to disk in blocks
fs=${FOCAL_SIZE:-5}  # focal window (cells per side, odd)
fm=${FOCAL_METHOD:-mean}  # focal statistic: mean or median (Whitebox median: values binned to SIG_DIGITS decimals,
                          # default 4 = 0.1 mm, comparable to the Float32 precision of the others; still approximate)
FM=$([ $fm = median ] && echo Median || echo Mean)
# algebra (ops_expr.py) and series (12-layer stack data/series/<res>m/s<k>.tif, prep_series.sh; SERIES_SET=<name>:
# the stack data/series/<res>m_<name>/, output <op>_<name>_<pkg>_<res>m)
sd=data/series/${1}m${SERIES_SET:+_$SERIES_SET} sl=$(for k in $(seq 12); do printf "%s;" "$sd/s$k.tif"; done) sl=${sl%;}
qco="COMPRESS=DEFLATE|BIGTIFF=IF_SAFER"  # QGIS creation options, | separated
wpre="import whitebox_workflows as wb; wbe = wb.WbEnvironment(); d = wbe.read_raster('$d');"
case $PKG/$OP in
    terra/relief) c=(rs "$pre s <- terrain(r, c('slope', 'aspect'), unit = 'radians'); h <- shade(s[[1]], s[[2]], angle = 30, direction = 270); writeRaster(h, '$o.tif', overwrite = TRUE, gdal = c('COMPRESS=LZW', 'NUM_THREADS=${NTHREADS:-16}'))") ;;
    terra/slope) c=(rs "$pre s <- terrain(r, c('slope', 'aspect'), unit = 'degrees', neighbors = 8); writeRaster(s, '$o.tif', overwrite = TRUE, gdal = c('COMPRESS=LZW', 'NUM_THREADS=${NTHREADS:-16}'))") ;;
    terra/focal) c=(rs "$pre f <- focal(r, w = $fs, fun = '$fm', na.rm = ${TERRA_NARM:-TRUE}); writeRaster(f, '$o.tif', overwrite = TRUE, gdal = c('COMPRESS=LZW', 'NUM_THREADS=${NTHREADS:-16}'))") ;;
    saga/relief) c=($S/bin/saga_cmd --cores=${NTHREADS:-16} --flags=q ta_lighting 0 -ELEVATION=$d -SHADE=$o.sdat -AZIMUTH=270 -DECLINATION=30) ;;
    saga/slope) c=($S/bin/saga_cmd --cores=${NTHREADS:-16} --flags=q ta_morphometry 0 -ELEVATION=$d -SLOPE=$o.sdat -ASPECT=${o}_asp.sdat -METHOD=2 -UNIT_SLOPE=1) ;;
    saga/focal) c=($S/bin/saga_cmd --cores=${NTHREADS:-16} --flags=q statistics_grid 1 -GRID=$d -$(echo $fm | tr a-z A-Z)=$o.sdat -KERNEL_TYPE=0 -KERNEL_RADIUS=$(( (fs - 1) / 2 ))) ;;
    wbw/relief) c=(wb "$wpre h = wbe.terrain.general.hillshade(input=d, azimuth=270.0, altitude=30.0); wbe.write_raster(h, '$o.tif')") ;;
    wbw/slope) c=(wb "$wpre s = wbe.slope(input=d, units='degrees'); a = wbe.aspect(input=d); wbe.write_raster(s, '$o.tif'); wbe.write_raster(a, '${o}_asp.tif')") ;;
    wbw/focal) c=(wb "$wpre f = wbe.remote_sensing.filters.${fm}_filter(input=d, filter_size_x=$fs, filter_size_y=$fs$([ $fm = median ] && echo ", sig_digits=${SIG_DIGITS:-4}")); wbe.write_raster(f, '$o.tif')") ;;
    wbt/relief) c=(wbt -r=Hillshade --dem=$d -o=$o.tif --azimuth=270 --altitude=30) ;;
    wbt/slope) c=(sh -c "$WBT $WBTF -r=Slope --dem=$d -o=$o.tif --units=degrees && $WBT $WBTF -r=Aspect --dem=$d -o=${o}_asp.tif") ;;
    wbt/focal) c=(wbt -r=${FM}Filter -i=$d -o=$o.tif --filterx=$fs --filtery=$fs $([ $fm = median ] && echo --sig_digits=${SIG_DIGITS:-4})) ;;
    gdal/relief) c=($Q/bin/gdaldem hillshade -q -az 270 -alt 30 -compute_edges -co COMPRESS=DEFLATE $d $o.tif) ;;
    gdal/slope) c=(sh -c "$Q/bin/gdaldem slope -q -compute_edges -co COMPRESS=DEFLATE $d $o.tif && $Q/bin/gdaldem aspect -q -compute_edges -co COMPRESS=DEFLATE $d ${o}_asp.tif") ;;
    gdal/focal) c=($Q/bin/gdal raster neighbors -q --method $fm --kernel equal --size $fs --ot Float32 --co COMPRESS=DEFLATE --overwrite $d $o.tif) ;;
    xrs/resample | xrsdask/resample | tt/resample) c=(env NUMBA_NUM_THREADS=${NTHREADS:-16} OMP_NUM_THREADS=${NTHREADS:-16} GDAL_NUM_THREADS=${NTHREADS:-16} .venv-xrs/bin/python -I resample_py.py $PKG $d $o) ;;  # before the general xrs/tt case
    xrs/* | xrsdask/* | tt/*) c=(env NUMBA_NUM_THREADS=${NTHREADS:-16} OMP_NUM_THREADS=${NTHREADS:-16} .venv-xrs/bin/python -I ops_py.py $PKG $OP $d $o $r) ;;
    richdem/*) c=($PWD/mamba/root/envs/richdem/bin/python -I ops_py.py $PKG $OP $d $o) ;;
    saga/cost) c=(sh -c "$S/bin/saga_cmd --cores=${NTHREADS:-16} --flags=q grid_analysis 0 -DEST_TYPE=0 -DEST_POINTS=$C/start${COST_SITE:+_$COST_SITE}.shp -COST=$C/friction_${r}m.tif -ACCUMULATED=$o.sdat -ALLOCATION=${o}_alloc.sdat && $S/bin/saga_cmd --cores=${NTHREADS:-16} --flags=q grid_analysis 5 -SOURCE=$C/end${COST_SITE:+_$COST_SITE}.shp -DEM=$o.sdat -VALUES=NULL -POINTS=${o}_pts.shp -LINE=${o}_line.shp") ;;
    wbt/cost) c=(sh -c "$WBT $WBTF -r=CostDistance --source=$C/src_${r}m.tif --cost=$C/friction_${r}m.tif --out_accum=$o.tif --out_backlink=${o}_bl.tif && $WBT $WBTF -r=CostPathway --destination=$C/dst_${r}m.tif --backlink=${o}_bl.tif -o=${o}_path.tif") ;;
    # .sdat: WBW writes new rasters as classic TIFF, unreadable above 4 GiB (cost at Iceland 10 m is 7.3 GB)
    wbw/cost) c=(wb "$wpre dc = wbe.raster.distance_cost; dc.cost_distance(source=wbe.read_raster('$C/src_${r}m.tif'), cost=wbe.read_raster('$C/friction_${r}m.tif'), output='$o.sdat', backlink_output='${o}_bl.sdat'); dc.cost_pathway(destination=wbe.read_raster('$C/dst_${r}m.tif'), backlink='${o}_bl.sdat', output='${o}_path.sdat')") ;;
    terra/cost) c=(rs "$pre f <- rast('$C/friction0_${r}m.tif'); d <- costDist(f, target = 0); writeRaster(d, '$o.tif', overwrite = TRUE, gdal = c('COMPRESS=LZW', 'NUM_THREADS=${NTHREADS:-16}'))") ;;
    gdal/algebra) c=($Q/bin/gdal raster calc -q --input A=$d --calc "$(python3 ops_expr.py muparser A)" --ot Float32 --co COMPRESS=DEFLATE --overwrite --output $o.tif) ;;
    gdal/series) c=($Q/bin/gdal raster calc -q $(for k in $(seq 12); do printf -- "--input S%d=%s " $k $sd/s$k.tif; done) --calc "($(for k in $(seq 12); do printf "S%d+" $k; done | sed 's/+$//'))/12" --ot Float32 --co COMPRESS=DEFLATE --overwrite --output $o.tif) ;;
    terra/algebra) c=(rs "$pre f <- app(r, fun = function(x) $(python3 ops_expr.py r x)${TERRA_APP_CORES:+, cores = $TERRA_APP_CORES}); writeRaster(f, '$o.tif', overwrite = TRUE, gdal = c('COMPRESS=LZW', 'NUM_THREADS=${NTHREADS:-16}'))") ;;
    terra/series) c=(rs "${pre%%r <- *} s <- rast(strsplit('$sl', ';')[[1]]); m <- mean(s); writeRaster(m, '$o.tif', overwrite = TRUE, gdal = c('COMPRESS=LZW', 'NUM_THREADS=${NTHREADS:-16}'))") ;;
    saga/algebra) c=($S/bin/saga_cmd --cores=${NTHREADS:-16} --flags=q grid_calculus 1 -GRIDS=$d -RESULT=$o.sdat -FORMULA="$(python3 ops_expr.py saga a)") ;;
    saga/series) c=($S/bin/saga_cmd --cores=${NTHREADS:-16} --flags=q statistics_grid 4 -GRIDS="$sl" -MEAN=$o.sdat) ;;
    wbt/algebra) c=(wbt -r=RasterCalculator --statement="$(python3 ops_expr.py wbt "'$PWD/$d'")" -o=$PWD/$o.tif) ;;
    wbt/series) c=(wbt -r=AverageOverlay --inputs="$(echo "$sl" | sed "s|$sd|$PWD/$sd|g")" -o=$PWD/$o.tif) ;;
    wbw/algebra) c=(wb "$wpre f = wbe.raster.raster_calculator(expression=$(python3 ops_expr.py wb "'E'" | python3 -c 'import sys; print(repr(sys.stdin.read().strip()))'), inputs=[d]); wbe.write_raster(f, '$o.tif')") ;;
    # BigTIFF: the Float64 mean is 4.9 GB; WBW writes classic TIFF by default, unreadable above 4 GiB
    wbw/series) c=(wb "import whitebox_workflows as wb; wbe = wb.WbEnvironment(); s = [wbe.read_raster(f) for f in '$sl'.split(';')]; m = wbe.raster.average_overlay(input_rasters=s); wbe.write_raster(m, '$o.tif', options={'geotiff': {'bigtiff': True}})") ;;
    xrs/algebra | xrsdask/algebra | xrs/series | xrsdask/series) c=(env NUMBA_NUM_THREADS=${NTHREADS:-16} .venv-xrs/bin/python -I ops_py.py $PKG $OP $d $o $r) ;;
    # resample: bicubic (RS_METHOD) from data/elev_${RS_IN:-3}m.tif onto the grid of data/elev_<res>m.tif
    gdal/resample) c=($Q/bin/gdalwarp -q -overwrite -multi -wo NUM_THREADS=${NTHREADS:-16} ${GDAL_WM:+-wm $GDAL_WM} -r $([ "${RS_METHOD:-bicubic}" = bicubic ] && echo cubic || echo bilinear) -tr $(.venv-xrs/bin/python -c "import rasterio; t = rasterio.open('$d').transform; print(t.a, -t.e)") -te $(.venv-xrs/bin/python -c "import rasterio; b = rasterio.open('$d').bounds; print(b.left, b.bottom, b.right, b.top)") -ot Float32 -co COMPRESS=DEFLATE -co TILED=YES -co BIGTIFF=IF_SAFER data/elev_${RS_IN:-3}m.tif $o.tif) ;;
    terra/resample) c=(rs "suppressMessages(library(terra)); terraOptions(threads = ${NTHREADS:-16}, parallel = TRUE); x <- resample(rast('data/elev_${RS_IN:-3}m.tif'), rast('$d'), method = '$([ "${RS_METHOD:-bicubic}" = bicubic ] && echo cubic || echo bilinear)'); writeRaster(x, '$o.tif', overwrite = TRUE, gdal = c('COMPRESS=LZW', 'NUM_THREADS=${NTHREADS:-16}'))") ;;
    wbw/resample) c=(wb "import whitebox_workflows as wb; wbe = wb.WbEnvironment(); s = wbe.read_raster('data/elev_${RS_IN:-3}m.tif'); t = wbe.read_raster('$d'); x = wbe.remote_sensing.resample(inputs=[s], base=t, method='$([ "${RS_METHOD:-bicubic}" = bicubic ] && echo cc || echo bilinear)'); wbe.write_raster(x, '$o.tif')") ;;
    saga/resample) c=($S/bin/saga_cmd --cores=${NTHREADS:-16} --flags=q grid_tools 0 -INPUT=data/elev_${RS_IN:-3}m.tif -OUTPUT=$o.sdat -SCALE_DOWN=$([ "${RS_METHOD:-bicubic}" = bicubic ] && echo 2 || echo 1) -TARGET_DEFINITION=0 -TARGET_USER_SIZE=$(.venv-xrs/bin/python -c "import rasterio; print(rasterio.open('$d').transform.a)") $(.venv-xrs/bin/python -c "
import rasterio; s = rasterio.open('$d'); b, h = s.bounds, s.transform.a / 2
print(f'-TARGET_USER_XMIN={b.left + h} -TARGET_USER_XMAX={b.right - h} -TARGET_USER_YMIN={b.bottom + h} -TARGET_USER_YMAX={b.top - h}')") -TARGET_USER_FITS=0) ;;
    wbt/resample) c=(wbt -r=Resample -i=$PWD/data/elev_${RS_IN:-3}m.tif -o=$PWD/$o.tif --base=$PWD/$d --method=$([ "${RS_METHOD:-bicubic}" = bicubic ] && echo cc || echo bilinear)) ;;
    xrs/cost | xrsdask/cost) c=(env NUMBA_NUM_THREADS=${NTHREADS:-16} .venv-xrs/bin/python -I ops_py.py $PKG $OP $d $o $r) ;;
    # QGIS native (C++) algorithms through qgis_process; only relief, slope + aspect and series exist natively
    # V_ANGLE acts as the angle from the zenith in QGIS 4.2.3 native:hillshade: 60 gives the 30 degree altitude
    # of the others (with 30, r 0.996 with altitude 60 and |r| 0.944 with GRASS on ice10)
    qgis/relief) c=(qp native:hillshade --INPUT=$PWD/$d --AZIMUTH=270 --V_ANGLE=60 --CREATION_OPTIONS="$qco" --OUTPUT=$PWD/$o.tif) ;;
    qgis/slope) c=(bash -c "qp native:slope --INPUT=$PWD/$d --CREATION_OPTIONS='$qco' --OUTPUT=$PWD/$o.tif && qp native:aspect --INPUT=$PWD/$d --CREATION_OPTIONS='$qco' --OUTPUT=$PWD/${o}_asp.tif") ;;
    qgis/series) c=(qp native:cellstatistics $(for k in $(seq 12); do printf -- "--INPUT=%s " $PWD/$sd/s$k.tif; done) --STATISTIC=2 --REFERENCE_LAYER=$PWD/$sd/s1.tif --CREATION_OPTIONS="$qco" --OUTPUT=$PWD/$o.tif) ;;
    # raster_tools, xDEM, scikit-image, Landlab, PCRaster, pyflwdir (ops_cand.py), gdistance, Orfeo ToolBox 9.1.1
    rt/* | xdem/* | xdemmp/* | xdemmpw/* | skimage/* | landlab/*) c=(env NUMBA_NUM_THREADS=${NTHREADS:-16} OMP_NUM_THREADS=${NTHREADS:-16} MPLCONFIGDIR=$PWD/out/ops/.mpl .venv-cand/bin/python -I ops_cand.py $PKG $OP $r $o) ;;
    pcraster/* | pcrastermc/*) c=(env OMP_NUM_THREADS=${NTHREADS:-16} $PWD/mamba/root/envs/pcraster/bin/python -I ops_cand.py $PKG $OP $r $o) ;;
    gdistance/cost) c=(env PROJ_DATA=$PWD/mamba/root/envs/gdistance/share/proj GDAL_DATA=$PWD/mamba/root/envs/gdistance/share/gdal $PWD/mamba/root/envs/gdistance/bin/Rscript cost_gdistance.R $C/friction_${r}m.tif ${COST_START:-1122385,-2618715} ${COST_END:-1206305,-2388085} $o) ;;
    # OTB streams with its default RAM hint (256 MB); ITK threads = NTHREADS
    otb/algebra) c=(bash -c ". otb/otbenv_bench.sh; ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=${NTHREADS:-16} otbcli_BandMath -il $d -exp '$(python3 ops_expr.py muparser im1b1)' -out '$o.tif?&gdal:co:COMPRESS=DEFLATE&gdal:co:TILED=YES&gdal:co:BIGTIFF=IF_SAFER' float") ;;
    otb/series) c=(bash -c ". otb/otbenv_bench.sh; ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=${NTHREADS:-16} otbcli_BandMath -il ${sl//;/ } -exp '($(for k in $(seq 12); do printf "im%db1+" $k; done | sed 's/+$//'))/12' -out '$o.tif?&gdal:co:COMPRESS=DEFLATE&gdal:co:TILED=YES&gdal:co:BIGTIFF=IF_SAFER' float") ;;
    # otb/focal: BandMathX neighbourhoods are at most 21 x 21 (m_SizeNeighbourhood = 10, not settable): run with
    # FOCAL_SIZE=21 (02_runs.sh), flagged approximate in Figure 2
    otb/focal) c=(bash -c ". otb/otbenv_bench.sh; ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=${NTHREADS:-16} otbcli_BandMathX -il $d -exp '$fm(im1b1N${fs}x${fs})' -out '$o.tif?&gdal:co:COMPRESS=DEFLATE&gdal:co:TILED=YES&gdal:co:BIGTIFF=IF_SAFER' float") ;;
    pyflwdir/cost) c=(env NUMBA_NUM_THREADS=${NTHREADS:-16} .venv/bin/python -I ops_cand.py pyflwdir cost $r $o) ;;  # cost surface, no path
    otb/resample) c=(bash -c ". otb/otbenv_bench.sh; ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS=${NTHREADS:-16} otbcli_Superimpose -inr $d -inm data/elev_${RS_IN:-3}m.tif -interpolator bco -out '$o.tif?&gdal:co:COMPRESS=DEFLATE&gdal:co:TILED=YES&gdal:co:BIGTIFF=IF_SAFER' float") ;;
    # GeoTools 33.5: geotools/Ops.java with the jars of envs/sedona_jars (Jiffle from Sedona's shaded jar)
    # geotools_c2g: JAI tile cache 2 GB instead of 64 MB (a GeoTools setting); geotoolspar: our code computes the tiles
    # on NTHREADS threads before writing (relief, focal, resample; 2 GB cache), a GeoTools candidate flagged user in Figure 2
    geotools/relief | geotools/focal | geotools/resample | geotools/algebra | geotools/series | geotools_c2g/resample | \
    geotoolspar/relief | geotoolspar/focal | geotoolspar/resample)
        c=(env NTHREADS=${NTHREADS:-16} FOCAL_SIZE=${FOCAL_SIZE:-5} $(case $PKG in geotools_c2g) echo GT_TILECACHE_MB=2048 ;;
           geotoolspar) echo GT_PARALLEL=1 GT_TILECACHE_MB=2048 ;; esac) java -cp envs/sedona_jars/geotools-wrapper-1.9.1-33.5.jar:envs/sedona_jars/sedona-spark-shaded-4.1_2.13-1.9.1.jar geotools/Ops.java $OP $d $o.tif
           "$(case $OP in resample) echo data/elev_${RS_IN:-3}m.tif ;; algebra) python3 ops_expr.py muparser A ;; series) echo $sd ;; esac)") ;;
    *) echo "no $PKG/$OP" >&2; exit 2 ;;
esac
rs() { PROJ_DATA=$R/share/proj GDAL_DATA=$R/share/gdal $R/bin/Rscript -e "$1"; }
wb() { RAYON_NUM_THREADS=${NTHREADS:-16} .venv-wbng/bin/python -I -c "$1"; }  # rayon's default: all CPUs it can see
wbt() { $WBT $WBTF "$@"; }
qp() { QT_QPA_PLATFORM=offscreen XDG_RUNTIME_DIR=${TMPDIR:-/tmp} QGIS_CUSTOM_CONFIG_PATH=$PWD/qgis_profile $Q/bin/qgis_process run "$@"; }
export -f rs wb wbt qp; export R WBT WBTF Q  # WBTF: wbt() runs in the bash -c below
[ "${PIN:-0-15}" = all ] && pin= || pin="taskset -c ${PIN:-0-15}"
$pin /usr/bin/time -f '%e %M %x %U %S' -o $TIMEFILE bash -c '"$@"' _ "${c[@]}"
