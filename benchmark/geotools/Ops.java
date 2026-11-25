// GeoTools candidate (2026-11-13): java -cp <geotools-wrapper jar>:<sedona-spark-shaded jar> geotools/Ops.java <op> <dem.tif> <out.tif> [arg]
// op = relief | focal | resample | algebra | series. Uses the GeoTools coverage operations (jai-ext ShadedRelief, JAI
// MedianFilter, Operations.resample with JAI bicubic) and Jiffle for algebra and series (GeoTools' raster algebra; the
// copy shaded into Sedona's jar, since the GeoTools wrapper jar does not include it). Jars: envs/sedona_jars (Sedona 1.9.1,
// GeoTools 33.5). arg: resample = the coarser input GeoTIFF; series = the directory with s1.tif .. s12.tif;
// algebra = the Jiffle expression of the source "A" (ops_expr.py muparser A). Output: tiled Deflate BigTIFF, Float32.
// Threads: JAI tile scheduler parallelism = NTHREADS (default 8), but the GeoTIFF writer requests one tile at a time, so
// the default runs use about one core; Jiffle runs on one thread. GT_PARALLEL=1 (side test, our code, not a GeoTools
// setting): relief, focal and resample compute all output tiles on NTHREADS threads into an in-memory image first,
// then write it (output held in memory). Prints read / compute+write.
import java.awt.Rectangle;
import java.awt.image.*;
import java.io.File;
import java.util.concurrent.ForkJoinPool;
import java.util.stream.IntStream;
import javax.media.jai.*;
import org.apache.sedona.shaded.jiffle.JiffleBuilder;
import org.geotools.api.parameter.GeneralParameterValue;
import org.geotools.api.parameter.ParameterValueGroup;
import org.geotools.coverage.grid.GridCoverage2D;
import org.geotools.coverage.grid.GridCoverageFactory;
import org.geotools.coverage.grid.io.AbstractGridFormat;
import org.geotools.coverage.processing.CoverageProcessor;
import org.geotools.coverage.processing.Operations;
import org.geotools.gce.geotiff.GeoTiffFormat;
import org.geotools.gce.geotiff.GeoTiffReader;
import org.geotools.gce.geotiff.GeoTiffWriteParams;
import org.geotools.gce.geotiff.GeoTiffWriter;
import it.geosolutions.jaiext.range.RangeFactory;
import it.geosolutions.jaiext.shadedrelief.ShadedReliefAlgorithm;

public class Ops {
    static long t0 = System.nanoTime();

    static void stamp(String what) {
        long t = System.nanoTime();
        System.out.printf("%s: %.2f s%n", what, (t - t0) / 1e9);
        t0 = t;
    }

    static GridCoverage2D read(String p) throws Exception {
        return new GeoTiffReader(new File(p)).read(null);
    }

    static void write(GridCoverage2D c, String p) throws Exception {
        GeoTiffWriteParams wp = new GeoTiffWriteParams();
        wp.setCompressionMode(GeoTiffWriteParams.MODE_EXPLICIT);
        wp.setCompressionType("Deflate");
        wp.setTilingMode(GeoTiffWriteParams.MODE_EXPLICIT);
        wp.setTiling(256, 256);
        wp.setForceToBigTIFF(true);
        ParameterValueGroup g = new GeoTiffFormat().getWriteParameters();
        g.parameter(AbstractGridFormat.GEOTOOLS_WRITE_PARAMS.getName().toString()).setValue(wp);
        GeoTiffWriter w = new GeoTiffWriter(new File(p));
        w.write(c, g.values().toArray(new GeneralParameterValue[0]));
        w.dispose();
    }

    static TiledImage floatImage(int w, int h) {
        SampleModel sm = RasterFactory.createBandedSampleModel(DataBuffer.TYPE_FLOAT, 256, 256, 1);
        return new TiledImage(0, 0, w, h, 0, 0, sm, PlanarImage.createColorModel(sm));
    }

    static GridCoverage2D jiffle(String script, String[] names, GridCoverage2D[] srcs) throws Exception {
        RenderedImage r0 = srcs[0].getRenderedImage();
        JiffleBuilder b = new JiffleBuilder().script(script);
        for (int i = 0; i < names.length; i++) b.source(names[i], srcs[i].getRenderedImage());
        TiledImage d = floatImage(r0.getWidth(), r0.getHeight());  // JiffleBuilder keeps only a weak reference
        b.dest("dest", d);
        b.run();
        return new GridCoverageFactory().create("dest", d, srcs[0].getEnvelope());
    }

    /** GT_PARALLEL: every 256 x 256 output tile computed on nt threads (getData on the deferred JAI chain). */
    static GridCoverage2D parallel(GridCoverage2D r, int nt) throws Exception {
        RenderedImage src = r.getRenderedImage();
        SampleModel sm = src.getSampleModel().createCompatibleSampleModel(256, 256);
        TiledImage d = new TiledImage(src.getMinX(), src.getMinY(), src.getWidth(), src.getHeight(), src.getMinX(),
                src.getMinY(), sm, src.getColorModel());
        int nx = d.getNumXTiles(), ny = d.getNumYTiles();
        ForkJoinPool pool = new ForkJoinPool(nt);
        pool.submit(() -> IntStream.range(0, nx * ny).parallel().forEach(i -> {
            Rectangle t = d.getTileRect(d.getMinTileX() + i % nx, d.getMinTileY() + i / nx);
            d.setData(src.getData(t));
        })).get();
        pool.shutdown();
        return new GridCoverageFactory().create(r.getName(), d, r.getEnvelope(), r.getSampleDimensions(), null,
                r.getProperties());
    }

    public static void main(String[] a) throws Exception {
        it.geosolutions.jaiext.JAIExt.initJAIEXT();
        int nt = Integer.parseInt(System.getenv().getOrDefault("NTHREADS", "8"));
        JAI.getDefaultInstance().getTileScheduler().setParallelism(nt);
        JAI.getDefaultInstance().getTileScheduler().setPrefetchParallelism(nt);
        String cache = System.getenv("GT_TILECACHE_MB");  // JAI tile cache, default 64 MB
        if (cache != null) JAI.getDefaultInstance().getTileCache().setMemoryCapacity(Long.parseLong(cache) << 20);
        String op = a[0], dem = a[1], out = a[2];
        CoverageProcessor P = CoverageProcessor.getInstance();
        GridCoverage2D c = read(dem), r;
        stamp("read (header, deferred)");
        switch (op) {
            case "relief" -> {
                ParameterValueGroup q = P.getOperation("ShadedRelief").getParameters();
                q.parameter("source").setValue(c);
                q.parameter("srcNoData").setValue(RangeFactory.create(-9999f, -9999f));
                double rx = c.getEnvelope2D().getWidth() / c.getRenderedImage().getWidth();
                double ry = c.getEnvelope2D().getHeight() / c.getRenderedImage().getHeight();
                q.parameter("resX").setValue(rx);
                q.parameter("resY").setValue(ry);
                q.parameter("dstNoData").setValue(-9999.0);
                q.parameter("altitude").setValue(30.0);
                q.parameter("azimuth").setValue(270.0);
                q.parameter("algorithm").setValue(ShadedReliefAlgorithm.DEFAULT);
                r = (GridCoverage2D) P.doOperation(q);
            }
            case "focal" -> {
                ParameterValueGroup q = P.getOperation("MedianFilter").getParameters();
                q.parameter("source").setValue(c);
                q.parameter("maskSize").setValue(Integer.parseInt(System.getenv().getOrDefault("FOCAL_SIZE", "25")));
                r = (GridCoverage2D) P.doOperation(q);
            }
            case "resample" -> {
                GridCoverage2D s = read(a[3]);
                r = (GridCoverage2D) Operations.DEFAULT.resample(s, c.getCoordinateReferenceSystem(), c.getGridGeometry(),
                        Interpolation.getInstance(Interpolation.INTERP_BICUBIC));
            }
            case "algebra" -> r = jiffle("dest = " + a[3] + ";", new String[] {"A"}, new GridCoverage2D[] {c});
            case "series" -> {
                String[] n = new String[12];
                GridCoverage2D[] s = new GridCoverage2D[12];
                StringBuilder sum = new StringBuilder();
                for (int k = 1; k <= 12; k++) {
                    n[k - 1] = "s" + k;
                    s[k - 1] = read(a[3] + "/s" + k + ".tif");
                    sum.append(k > 1 ? " + " : "").append("s").append(k);
                }
                r = jiffle("dest = (" + sum + ") / 12;", n, s);
            }
            default -> {
                System.err.println("no " + op + " in GeoTools");
                System.exit(3);
                return;
            }
        }
        if ("1".equals(System.getenv("GT_PARALLEL")) && !op.equals("algebra") && !op.equals("series")) {
            stamp("set up");
            r = parallel(r, nt);
        }
        stamp("set up (jiffle, parallel: computed)");
        write(r, out);
        stamp("compute + write");
    }
}
