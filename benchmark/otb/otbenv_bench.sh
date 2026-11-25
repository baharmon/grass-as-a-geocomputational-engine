# OTB 9.1.1 environment for the benchmark: otbenv.profile without its post-install step, which retries a download
# of GDAL Python bindings on every launch (not needed for otbcli_*) and waits for the network timeout (~60 s)
O=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
export OTB_INSTALL_DIR=$O OTB_APPLICATION_PATH=$O/lib/otb/applications PATH=$O/bin:$PATH LD_LIBRARY_PATH=$O/lib
export GDAL_DATA=$O/share/gdal PROJ_LIB=$O/share/proj PROJ_DATA=$O/share/proj GDAL_DRIVER_PATH=disable LC_NUMERIC=C
