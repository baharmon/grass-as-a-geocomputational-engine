#!/usr/bin/env bash
# Optimized build of the same GRASS source as the dev tree (dev tree: -O0 -ggdb).
set -e
cd "$(dirname "$0")"
./configure --with-cxx --enable-largefile --with-proj-share=/usr/share/proj \
    --with-gdal=/usr/bin/gdal-config --with-geos --with-sqlite --with-nls --with-zstd \
    --without-pdal --with-bzlib --with-netcdf --with-readline --with-cairo \
    --with-cairo-ldflags=-lfontconfig --with-freetype=yes \
    --with-freetype-includes=/usr/include/freetype2/ --with-fftw \
    --with-opengl-libs=/usr/include/GL --with-postgres=yes \
    --with-postgres-includes=/usr/include/postgresql --without-mysql --without-odbc \
    --with-pthread --with-libsvm --with-openmp \
    CFLAGS="-O2" CXXFLAGS="-O2" LDFLAGS="-Wl,--no-undefined -Wl,-z,now" >configure.log 2>&1
make -j32 >make.log 2>&1
