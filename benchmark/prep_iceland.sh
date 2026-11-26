#!/usr/bin/env bash
# Prepare the Iceland ArcticDEM 10 m inputs (01_data.sh). Run inside a temporary mapset of the
# source project (data/raw/iceland), so its PERMANENT stays untouched:
#   OUT=data/nan_originals grass --tmp-mapset data/raw/iceland --exec bash prep_iceland.sh
# 1. Region = bounding box of the landmass polygon (vector `iceland`, Natural Earth), 10 m grid.
# 2. DEM masked to the polygon: the sea (values in the raw mosaic) becomes no-data.
# 3. The 58,042 void cells inside the polygon (87 patches, largest 39,961 cells) are filled with
#    the nearest valid elevation (r.grow.distance), which makes small flat patches.
# 4. Export 10 m and averaged 20/50/100 m versions (r.resamp.stats, nulls ignored) as Float32
#    GeoTIFFs with NaN no-data, deflate, 256 x 256 tiles: $OUT/elev_ice<res>m.tif (01_data.sh then sets -9999).
set -e
out=${OUT:-$PWD/data}
g.region raster=iceland
v.to.rast --q --o input=iceland output=land use=val value=1
g.region zoom=land
r.mapcalc --q --o "dem_raw = if(isnull(land), null(), iceland)"
r.grow.distance --q --o input=dem_raw value=dem_nearest
r.mapcalc --q --o "dem = float(if(isnull(land), null(), if(isnull(dem_raw), dem_nearest, dem_raw)))"
opts="COMPRESS=DEFLATE,TILED=YES,BLOCKXSIZE=256,BLOCKYSIZE=256,BIGTIFF=YES"
r.out.gdal --q --o -c input=dem output="$out/elev_ice10m.tif" type=Float32 createopt="$opts"
r.univar -g map=dem | grep -E "^(n|null_cells|min|max)=" | sed 's/^/10m /'
g.region -g | grep -E "^(rows|cols|cells)=" | sed 's/^/10m /'
for res in 20 50 100; do
    g.region raster=dem res=$res -a
    r.resamp.stats --q --o input=dem output=dem_${res}d method=average
    r.mapcalc --q --o "dem_$res = float(dem_${res}d)"
    r.out.gdal --q --o -c input=dem_$res output="$out/elev_ice${res}m.tif" type=Float32 createopt="$opts"
    r.univar -g map=dem_$res | grep -E "^(n|null_cells)=" | sed "s/^/${res}m /"
    g.region -g | grep -E "^(rows|cols|cells)=" | sed "s/^/${res}m /"
done
