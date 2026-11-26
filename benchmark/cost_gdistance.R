# Least-cost distance and path with gdistance (R, 2026-11-12 candidate run; tools/ops_other.sh PKG=gdistance OP=cost).
# Rscript cost_gdistance.R <friction.tif> <start x,y> <end x,y> <out prefix>
# Transition matrix of 8 neighbours with conductance 1 / mean(friction), geoCorrection for cell distances (diagonal
# x sqrt(2)), accumulated cost from the start (accCost) and the shortest path to the end (shortestPath). gdistance
# works on raster package objects, so the friction is read with raster (terra is used only to write the output).
args <- commandArgs(trailingOnly = TRUE)
suppressMessages({library(raster); library(gdistance); library(terra)})
t0 <- Sys.time()
stamp <- function(what) {t <- Sys.time(); cat(sprintf("%s: %.2f s\n", what, as.numeric(t - t0, units = "secs"))); t0 <<- t}
f <- raster(args[1])
s <- as.numeric(strsplit(args[2], ",")[[1]]); e <- as.numeric(strsplit(args[3], ",")[[1]])
stamp("read")
tr <- geoCorrection(transition(f, function(x) 1 / mean(x), directions = 8), type = "c")
stamp("transition")
S <- sp::SpatialPoints(matrix(s, ncol = 2), proj4string = crs(f)); E <- sp::SpatialPoints(matrix(e, ncol = 2), proj4string = crs(f))
a <- gdistance::accCost(tr, S)
stamp("accCost")
p <- gdistance::shortestPath(tr, S, E, output = "SpatialLines")
stamp("shortestPath")
writeRaster(rast(a), paste0(args[4], ".tif"), overwrite = TRUE, gdal = c("COMPRESS=DEFLATE", "BIGTIFF=IF_SAFER"))
writeVector(vect(p), paste0(args[4], "_path.gpkg"), overwrite = TRUE)
stamp("write")
