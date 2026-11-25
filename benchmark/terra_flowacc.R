# Flow accumulation with terra: D8 flow direction on the DEM as given (terra has no depression
# filling), then flowAccumulation. Usage: Rscript terra_flowacc.R <dem.tif> <out.tif> [dir.tif]
suppressMessages(library(terra))
terraOptions(threads = as.integer(Sys.getenv("NTHREADS", "16")), parallel = TRUE)  # 2026-10-30
a <- commandArgs(TRUE)
t0 <- Sys.time()
dem <- rast(a[1])
fdir <- terrain(dem, v = "flowdir")
acc <- flowAccumulation(fdir)
writeRaster(acc, a[2], overwrite = TRUE, gdal = c("COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=YES"))
if (length(a) > 2) writeRaster(fdir, a[3], overwrite = TRUE, datatype = "INT1U")
cat(sprintf("terra %s total=%.1fs\n", packageVersion("terra"), as.numeric(Sys.time() - t0, units = "secs")))
