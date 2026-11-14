"""The overview map behind the spot list: every region's coastline and depth bands on one map, from
the same regional depth grids the model uses (so no map tiles to license). Rebuilt nightly.

Coordinates are metres east/north of one reference point (`frame`), like the spot maps; the client
places spots with the same formula: x = (lon - lon0) * mx, y = (lat - lat0) * my.
"""
import os
from types import SimpleNamespace
import numpy as np
import config
from common import Bathy
from . import SCHEMA_VERSION
from .geometry import Frame, land_polygons

TOL_M = 180            # simplify outlines to this (the regional grids are ~90 m)

def _regions():
    return [r for r in config.REGIONS if os.path.exists(config.coarse_path(r))
            and any(os.path.exists(config.table_path(s["slug"])) for s in config.load_spots(r, "spot"))]

def overview_map():
    regions = _regions()
    if not regions:
        return None
    boxes = {r: config.REGIONS[r]["bbox"] for r in regions}      # lat_s, lat_n, lon_w, lon_e
    lat0 = (min(b[0] for b in boxes.values()) + max(b[1] for b in boxes.values())) / 2
    lon0 = (min(b[2] for b in boxes.values()) + max(b[3] for b in boxes.values())) / 2
    frame = Frame(lat0, lon0)
    # neighbouring grids overlap a little: split each overlap at its middle so nothing is drawn twice
    order = sorted(regions, key=lambda r: -boxes[r][1])           # north to south
    cut = {r: [boxes[r][0], boxes[r][1]] for r in regions}
    for a, b in zip(order, order[1:]):
        if boxes[b][1] > boxes[a][0]:
            mid = (boxes[a][0] + boxes[b][1]) / 2
            cut[a][0], cut[b][1] = mid, mid
    out = []
    for r in order:
        g = Bathy.coarse(r)
        j = (g.lat >= cut[r][0]) & (g.lat <= cut[r][1])
        sub = SimpleNamespace(lat=g.lat[j], lon=g.lon, z=g.z[j])
        land, bands, _ = land_polygons(sub, frame, None, TOL_M)
        x0, y0 = frame.xy(sub.lat[0], sub.lon[0]); x1, y1 = frame.xy(sub.lat[-1], sub.lon[-1])
        out.append(dict(region=r, name=config.REGIONS[r]["name"], box=[round(float(x0)), round(float(x1)), round(float(y0)), round(float(y1))],
                        land=land, bands=[b for b in bands if b["depth"] in (50, 100)]))
    return dict(schema_version=SCHEMA_VERSION, frame=dict(lat=round(lat0, 5), lon=round(lon0, 5),
                mx=round(frame.mx, 3), my=frame.my), regions=out)
