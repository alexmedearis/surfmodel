"""The overview map behind the spot list: every region's coastline and depth bands on one map, from
the same regional depth grids the model uses (so no map tiles to license): a shaded-relief image per
region and theme (overview/<region>-<light|dark>.webp) with vector coastlines on top. Rebuilt nightly.

Coordinates are metres east/north of one reference point (`frame`), like the spot maps; the client
places spots with the same formula: x = (lon - lon0) * mx, y = (lat - lat0) * my.
"""
import io, os
from types import SimpleNamespace
import numpy as np
from PIL import Image
import config
from common import Bathy
from . import SCHEMA_VERSION
from .geometry import Frame, land_polygons

TOL_M = 180            # simplify outlines to this (the regional grids are ~90 m)
THEMES = ("light", "dark")

# Shaded relief colors: (depth or height in m, RGB). Sea by depth, land by height, per theme.
_SEA = {"light": [(0, (196, 230, 240)), (15, (160, 212, 232)), (50, (120, 186, 220)), (150, (84, 150, 200)),
                  (600, (58, 116, 172)), (2000, (40, 88, 142)), (4000, (30, 68, 116))],
        "dark":  [(0, (34, 74, 98)), (15, (28, 62, 86)), (50, (22, 50, 74)), (150, (17, 40, 62)),
                  (600, (13, 31, 50)), (2000, (10, 24, 40)), (4000, (8, 18, 32))]}
_LAND = {"light": [(0, (236, 231, 214)), (60, (226, 223, 200)), (250, (210, 208, 180)), (700, (190, 182, 154)), (1500, (176, 164, 140))],
         "dark":  [(0, (52, 56, 58)), (60, (56, 60, 58)), (250, (62, 64, 60)), (700, (70, 68, 62)), (1500, (78, 74, 68))]}

def _ramp(v, stops):
    xs = [a for a, _ in stops]
    return np.stack([np.interp(v, xs, [c[k] for _, c in stops]) for k in range(3)], -1)

def _hillshade(z, dx, dy, az=315, alt=40, exaggerate=1.0):
    gy, gx = np.gradient(z * exaggerate, dy, dx)                 # rows run south -> north
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, e = np.radians(az), np.radians(alt)
    hs = np.sin(e) * np.cos(slope) + np.cos(e) * np.sin(slope) * np.cos(a - aspect)
    return np.clip(hs, 0, 1)

def relief_image(grid, theme, fade=None, fmt="WEBP"):
    """Shaded relief of a depth grid as image bytes (north up): hillshaded land colored by height,
    the seafloor colored by depth with gentler shading (canyons and banks show), edges faded out.
    `fade`: {"n"|"s": bool per column, "e"|"w": bool per row}: where that edge fades (default all of it),
    so it stays sharp only where a neighbouring region carries on."""
    z = grid.z
    dx = float(np.mean(np.diff(grid.lon))) * 111320 * np.cos(np.radians(grid.lat.mean()))
    dy = float(np.mean(np.diff(grid.lat))) * 110540
    land = z > 0
    rgb = np.where(land[..., None], _ramp(np.maximum(z, 0), _LAND[theme]), _ramp(np.maximum(-z, 0), _SEA[theme]))
    hs_land = _hillshade(np.where(land, z, 0), dx, dy, exaggerate=2.0)
    hs_sea = _hillshade(np.where(land, 0, z), dx, dy, exaggerate=6.0)
    shade = np.where(land, 0.62 + 0.55 * hs_land, 0.80 + 0.30 * hs_sea)
    if theme == "dark":
        shade = np.where(land, 0.55 + 0.75 * hs_land, 0.75 + 0.40 * hs_sea)
    rgb = np.clip(rgb * shade[..., None], 0, 255)
    # fade the outer edges into the page so each region sits on it like an island
    ny, nx = z.shape
    alpha = np.ones((ny, nx))
    fx, fy = max(4, nx // 18), max(4, ny // 18)
    ramp = lambda n: (1 - np.cos(np.linspace(0, np.pi, n))) / 2
    fade = fade or {}
    on = lambda e, n: np.asarray(fade.get(e, np.ones(n, bool)), float)
    w, e, sth, nth = on("w", ny), on("e", ny), on("s", nx), on("n", nx)
    alpha[:, :fx] *= 1 - w[:, None] * (1 - ramp(fx)[None, :])
    alpha[:, -fx:] *= 1 - e[:, None] * (1 - ramp(fx)[None, ::-1])
    alpha[:fy, :] *= 1 - sth[None, :] * (1 - ramp(fy)[:, None])
    alpha[-fy:, :] *= 1 - nth[None, :] * (1 - ramp(fy)[::-1, None])
    img = np.dstack([rgb, alpha * 255]).astype(np.uint8)[::-1]       # row 0 = north
    buf = io.BytesIO()
    Image.fromarray(img, "RGBA").save(buf, fmt, quality=82, method=6)
    return buf.getvalue()

def _regions():
    return [r for r in config.REGIONS if os.path.exists(config.coarse_path(r))
            and any(os.path.exists(config.table_path(s["slug"])) for s in config.load_spots(r, "spot"))]

def overview_map():
    """(overview dict, {path: image bytes}) or (None, {})."""
    regions = _regions()
    if not regions:
        return None, {}
    boxes = {r: config.REGIONS[r]["bbox"] for r in regions}      # lat_s, lat_n, lon_w, lon_e
    lat0 = (min(b[0] for b in boxes.values()) + max(b[1] for b in boxes.values())) / 2
    lon0 = (min(b[2] for b in boxes.values()) + max(b[3] for b in boxes.values())) / 2
    frame = Frame(lat0, lon0)
    # neighbouring grids overlap a little: keep a thin band of the overlap in both and cross-fade there
    # (the northern image fades out over the southern one, which the client draws underneath)
    order = sorted(regions, key=lambda r: -boxes[r][1])           # north to south
    cut = {r: [boxes[r][0], boxes[r][1]] for r in regions}
    for a, b in zip(order, order[1:]):
        if boxes[b][1] > boxes[a][0]:
            mid, band = (boxes[a][0] + boxes[b][1]) / 2, min(0.05, (boxes[b][1] - boxes[a][0]) / 2)
            cut[a][0], cut[b][1] = mid - band, mid + band
    out, images = [], {}
    for r in order:
        g = Bathy.coarse(r)
        j = (g.lat >= cut[r][0]) & (g.lat <= cut[r][1])
        sub = SimpleNamespace(lat=g.lat[j], lon=g.lon, z=g.z[j])
        land, bands, _ = land_polygons(sub, frame, None, TOL_M)
        # the box spans the grid cells' outer edges, so the relief image lines up with the outlines
        hlat, hlon = float(np.mean(np.diff(sub.lat))) / 2, float(np.mean(np.diff(sub.lon))) / 2
        x0, y0 = frame.xy(sub.lat[0] - hlat, sub.lon[0] - hlon); x1, y1 = frame.xy(sub.lat[-1] + hlat, sub.lon[-1] + hlon)
        # fade every edge, except a southern region's top where the region above covers it (that one
        # fades out over it instead)
        fade = {}
        k = order.index(r)
        if k > 0 and cut[r][1] < boxes[r][1]:
            up = order[k - 1]
            inset = (boxes[up][3] - boxes[up][2]) / 18
            fade["n"] = (sub.lon < boxes[up][2] + inset) | (sub.lon > boxes[up][3] - inset)
        img = {}
        for th in THEMES:
            path = f"overview/{r}-{th}.webp"
            images[path] = relief_image(sub, th, fade)
            img[th] = path
        out.append(dict(region=r, name=config.REGIONS[r]["name"], box=[round(float(x0)), round(float(x1)), round(float(y0)), round(float(y1))],
                        land=land, bands=[b for b in bands if b["depth"] in (50, 100)], image=img))
    return dict(schema_version=SCHEMA_VERSION, frame=dict(lat=round(lat0, 5), lon=round(lon0, 5),
                mx=round(frame.mx, 3), my=frame.my), regions=out), images
