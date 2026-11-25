"""Raster algebra expression of the benchmark (OP=algebra), rendered in each package's dialect.
Usage: ops_expr.py <dialect> <input name>   dialects: grass, muparser (GDAL), saga, wb (WhiteboxTools and
Whitebox Workflows), r (terra app), numpy (xarray).

The expression uses only operations every dialect has (arithmetic, abs, square root, exponential), no
random numbers (r.mapcalc stays threaded), no graph()/trigonometry (r.mapcalc's sin() takes degrees) and no
conditional (computation only; until 2026-10-30 it also had two if()s with the sum in both branches). With
a = |E|:
    result = sum_{k=1..8} sqrt(a + k) * exp(-a / (500 k))    (32 function calls per cell)
Whitebox's calculator has no sqrt, exp, abs or unary minus, and cannot multiply a comparison: x^0.5,
e()^x, (x^2)^0.5 and 0 - x are used there (dialects wb and wbt are the same now that there is no if()).

Series statistics (OP=series): the mean of the 12-layer stack data/series/<res>m/s<k>.tif, layer k = E + k,
so the expected result is E + 6.5 (prep_series.sh).
"""

import sys

K = 8


def render(dialect, e):
    a = f"(({e})^2)^0.5" if dialect in ("wb", "wbt") else f"abs({e})"  # Whitebox: no abs()
    terms = []
    for k in range(1, K + 1):
        if dialect in ("wb", "wbt"):
            t = f"({a} + {k})^0.5 * e()^(0 - {a} / {500 * k})"  # Whitebox: no unary minus
        elif dialect == "numpy":
            t = f"np.sqrt(np.abs({e}) + {k}) * np.exp(-np.abs({e}) / {500 * k})"
        else:
            t = f"sqrt({a} + {k}) * exp(-{a} / {500 * k})"
        terms.append(t)
    if dialect not in ("grass", "muparser", "saga", "wb", "wbt", "r", "numpy"):
        raise SystemExit(f"unknown dialect {dialect}")
    return " + ".join(terms)  # no conditional (user, 2026-10-30): computation only


if __name__ == "__main__":
    print(render(sys.argv[1], sys.argv[2]))
