"""Regions and spots.

A region is one coarse (~90 m) bathymetry grid with a deep-water input buoy. Each spot
gets its own fine (~10 m) nearshore grid, nested inside its region's coarse grid.
Add spots by adding rows to spots.csv (kind=spot), then run fetch_bathy.py and
build_tables.py. Rows with kind=buoy are nearshore buoys used to check the model.
"""
import csv, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "out")

REGIONS = {
    "bayarea": dict(
        name="SF Bay Area",
        bbox=(37.0, 38.0, -123.40, -122.35),          # lat_s, lat_n, lon_w, lon_e
        input_buoy="029",                             # Point Reyes (deep water, unsheltered)
        forecast_point="46214",                       # WaveWatch III output at the same buoy
    ),
    "santacruz": dict(
        name="Santa Cruz / Monterey Bay",
        bbox=(36.45, 37.25, -122.65, -121.75),
        input_buoy="ndbc:46042",                      # NOAA Monterey, ~1,700 m deep, outside the bay
        forecast_point="46042",
    ),                                                # (CDIP 156 sits inside the bay, already sheltered)
    # Planned. Each needs its coarse grid fetched (fetch_bathy.py coarse <region>) and spots added.
    # SoCal needs a large domain so the Channel Islands' shadows are inside it.
    "northcoast": dict(name="North Coast", bbox=(39.4, 41.2, -124.90, -123.60), input_buoy="094"),

    "slo":        dict(name="San Luis Obispo", bbox=(34.6, 35.8, -121.60, -120.50), input_buoy="222"),
    "socal":      dict(name="Southern California", bbox=(32.4, 34.6, -121.00, -117.10), input_buoy="071"),
}

FINE_HALF_KM = 3.0        # fine grid extends this far from the spot in each direction
FINE_RES_DEG = 1 / 10800  # 1/3 arc-second, ~10 m
BREAK_DEPTH = 4.0         # surf height is computed here, in the breaking zone at the marked spot (m)
FINE_SMOOTH_M = 30.0      # smoothing for ray stability (features << a wavelength don't refract rays)

def coarse_path(region):
    return os.path.join(DATA, f"coarse_{region}.npz")

def fine_path(slug):
    return os.path.join(DATA, "fine", f"{slug}.npz")

def table_path(slug):
    return os.path.join(DATA, "tables", f"{slug}.json")

def load_spots(region=None, kind=None):
    with open(os.path.join(HERE, "spots.csv")) as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        r["lat"], r["lon"] = float(r["lat"]), float(r["lon"])
        r["depth"] = float(r["depth"]) if r["depth"] else None   # None: model at the exact point
        if (region is None or r["region"] == region) and (kind is None or r["kind"] == kind):
            out.append(r)
    return out
