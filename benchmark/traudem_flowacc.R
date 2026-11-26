# Flow accumulation with traudem (R wrapper of TauDEM): PitRemove, then D8 or D-infinity.
# D8: D8FlowDir (flats resolved with Garbrecht & Martz), AreaD8 without the edge-contamination
# mask (the other tools don't mask). dinf: DinfFlowDir + AreaDinf (-nc, no edge mask) through
# taudem_exec, since traudem wraps only the D8 tools; D-infinity splits flow between two neighbors.
# Usage: TAUDEM_PATH=... Rscript traudem_flowacc.R <dem.tif> <out.tif> [n_processes] [dir.tif] [routing]
suppressMessages(library(traudem))
a <- commandArgs(TRUE)
np <- if (length(a) > 2) as.integer(a[3]) else 1L
dir_out <- if (length(a) > 3 && nzchar(a[4])) a[4] else tempfile(fileext = ".tif")
routing <- if (length(a) > 4) a[5] else "d8"
tmp <- tempfile()
t0 <- Sys.time()
taudem_pitremove(a[1], paste0(tmp, "_fel.tif"), n_processes = np, quiet = TRUE)
if (routing == "dinf") {
  taudem_exec("dinfflowdir", c("-fel", paste0(tmp, "_fel.tif"), "-ang", dir_out, "-slp", paste0(tmp, "_slp.tif")),
              n_processes = np, quiet = TRUE)
  taudem_exec("areadinf", c("-ang", dir_out, "-sca", a[2], "-nc"), n_processes = np, quiet = TRUE)
} else {
  taudem_d8flowdir(paste0(tmp, "_fel.tif"), dir_out, paste0(tmp, "_sd8.tif"), n_processes = np, quiet = TRUE)
  taudem_aread8(dir_out, a[2], check_edge_contamination = FALSE, n_processes = np, quiet = TRUE)
}
cat(sprintf("traudem %s routing=%s n_processes=%d total=%.1fs\n", packageVersion("traudem"), routing, np,
            as.numeric(Sys.time() - t0, units = "secs")))
unlink(Sys.glob(paste0(tmp, "*")))
