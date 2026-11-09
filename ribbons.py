"""Swell ribbons: for each of today's swells, the real refracted paths its energy takes
into a spot, drawn as a ribbon whose width is the swell's height along the way.

  python ribbons.py [slug ...]                  -> out/ribbons_<slug>.html (open in a browser)
  python ribbons.py --at "2026-11-07 06:00"     replay the buoy reading nearest that UTC time
  python ribbons.py --hours-ago 24 linda-mar    or one about that long ago
  python ribbons.py --no-forecast               skip the 7-day forecast (always skipped with --at)

How a ribbon is built:
  1. Trace wave rays backward from the spot at the swell's peak period (10 m grid near
     shore, 90 m offshore), just like the transfer tables.
  2. Keep the rays that reach open ocean from directions this swell actually has energy in,
     weighted by that energy.
  3. Neighbouring rays that travel the same route form a strand; a swell that arrives by
     two routes (e.g. straight in, and wrapping around a point) gets two strands.
  4. Each strand's centre line is the energy-weighted mean of its rays: that curve is the
     real refraction. Width = the swell's estimated height along the path, from its
     offshore height down to what reaches the spot (a display choice, not ray spacing).
  A swell with almost nothing arriving is shown heading in from its direction, either
  stopping where the coast blocks it or running past the spot.
"""
import json, os, sys, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config
from common import Bathy, wavenumber
from raytrace import Tracer, compass_from, MIN_EXIT_DEPTH
import datetime as dt
from buoy import latest, nearest
from predict import load_tables, predict, swells, W_at, M2FT, surf_ft
from partition import label, compass
import forecast

VIEW_SEAWARD, VIEW_HALF = 5500, (9500, 10000)    # coast map: centred this far out to sea, ~19 x 20 km
COLORS = ["#1D9E75", "#D85A30", "#7F77DD", "#BA7517", "#D4537E"]
BLOCKED_FT = 0.5                                  # less than this arriving -> "blocked"

class Frame:
    """Local metres east/north of the spot, shared by both grids."""
    def __init__(self, lat, lon):
        self.lat, self.lon = lat, lon
        self.mx = 111320.0 * np.cos(np.radians(lat)); self.my = 110540.0
    def xy(self, lat, lon):
        return (np.asarray(lon) - self.lon) * self.mx, (np.asarray(lat) - self.lat) * self.my

def _paths_to_ll(grid, P):
    """Tracer path list -> per-ray (lat, lon) arrays without NaNs."""
    A = np.array(P)                                  # steps x 2 x rays
    la, lo = grid.to_ll(A[:, 0], A[:, 1])
    out = []
    for k in range(A.shape[2]):
        m = np.isfinite(la[:, k])
        out.append((la[m, k], lo[m, k]))
    return out

def backward(coarse, fine, T, lat, lon, th0, keep=False):
    """Nested backward rays from (lat, lon). Returns offshore 'from' direction (NaN when
    blocked) and, with keep, each ray's path as (lat, lon) from the spot outward."""
    trf, trc = Tracer(fine, T), Tracer(coarse, T)
    x0, y0 = fine.to_xy(lat, lon)
    n = th0.size
    xf, yf, thf, stf, pf = trf.trace(np.full(n, float(x0)), np.full(n, float(y0)), th0.copy(),
                                    ds=8.0, max_steps=4000, keep_path=keep)
    frm = np.full(n, np.nan)
    ex = np.flatnonzero(stf == 1)
    la, lo = fine.to_ll(xf[ex], yf[ex])
    cx, cy = coarse.to_xy(la, lo)
    xc, yc, thc, stc, pc = trc.trace(cx, cy, thf[ex].copy(), keep_path=keep)
    edepth = trc._interp(coarse.h, np.clip(xc, 0, coarse.width), np.clip(yc, 0, coarse.height))
    ok = (stc == 1) & (edepth > MIN_EXIT_DEPTH)
    frm[ex[ok]] = compass_from(thc[ok])
    paths = None
    if keep:
        fp, cp = _paths_to_ll(fine, pf), _paths_to_ll(coarse, pc)
        paths = [fp[i] for i in range(n)]
        for j, i in enumerate(ex):
            paths[i] = (np.concatenate([fp[i][0], cp[j][0]]), np.concatenate([fp[i][1], cp[j][1]]))
    return frm, paths

def resample(x, y, step):
    s = np.concatenate([[0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    t = np.arange(0, s[-1], step)
    return np.interp(t, s, x), np.interp(t, s, y)

def strands_for(coarse, fine, frame, tab, part, comp, view, ray_box=None, dtheta=0.1, max_strands=3):
    """Energy-weighted strands for one swell. Returns list of dicts with centre line (x, y
    from offshore to the spot, metres) and strand share of the arriving energy."""
    T = max(part["tp"], 6.0)
    dirs = np.arange(0, 360, 5.0)
    Sd = (part["S"] * part["mask"]).sum(0)          # this swell's energy by direction
    th0 = np.radians(np.arange(0, 360, dtheta))
    frm, _ = backward(coarse, fine, T, tab["lat"], tab["lon"], th0)
    w = np.zeros(th0.size)
    good = np.isfinite(frm)
    w[good] = np.interp(frm[good], np.r_[dirs, 360.0], np.r_[Sd, Sd[0]])
    if w.max() <= 0:
        return []
    w[w < 0.02 * w.max()] = 0
    idx = np.flatnonzero(w > 0)
    # contiguous runs in launch angle (wrapping) = candidate strands
    runs, cur = [], [idx[0]]
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a <= 2: cur.append(b)
        else: runs.append(cur); cur = [b]
    runs.append(cur)
    if len(runs) > 1 and runs[0][0] <= 1 and runs[-1][-1] >= th0.size - 2:
        runs[0] = runs.pop() + runs[0]
    runs = sorted(runs, key=lambda r: -w[r].sum())
    total = sum(w[r].sum() for r in runs)
    runs = [r for r in runs if w[r].sum() >= 0.1 * total][:max_strands]
    out = []
    for r in runs:
        r = np.array(r)
        sel = r[np.linspace(0, len(r) - 1, min(len(r), 40)).astype(int)]  # up to 40 rays per strand
        _, paths = backward(coarse, fine, T, tab["lat"], tab["lon"], th0[sel], keep=True)
        X, Y, W, rays = [], [], [], []
        for j, (k, (la, lo)) in enumerate(zip(sel, paths)):
            x, y = frame.xy(la, lo)
            if ray_box is not None and j % max(1, len(sel) // 12) == 0:   # ~12 individual rays for the close-up
                rx, ry = resample(x, y, 15.0)
                bx0, bx1, by0, by1 = ray_box
                ins = (rx >= bx0) & (rx <= bx1) & (ry >= by0) & (ry <= by1)
                stop = np.argmin(ins) if not ins.all() else len(rx)
                if stop > 2:
                    rays.append((np.round(rx[:stop][::-1]).astype(int).tolist(), np.round(ry[:stop][::-1]).astype(int).tolist()))
            x, y = resample(x, y, 40.0)
            X.append(x); Y.append(y); W.append(w[k])
        n = min(len(x) for x in X)
        Wn = np.array(W) / np.sum(W)
        cx = sum(wi * x[:n] for wi, x in zip(Wn, X)); cy = sum(wi * y[:n] for wi, y in zip(Wn, Y))
        x0, x1, y0, y1 = view
        inside = (cx >= x0) & (cx <= x1) & (cy >= y0) & (cy <= y1)
        stop = np.argmin(inside) if not inside.all() else len(cx)
        cx, cy = cx[:max(stop, 2)][::-1], cy[:max(stop, 2)][::-1]   # offshore -> spot
        a = np.radians(frm[r])
        dmean = np.degrees(np.arctan2((w[r] * np.sin(a)).sum(), (w[r] * np.cos(a)).sum())) % 360
        # direction the waves come from as they reach the spot (after all the bending): the
        # backward rays' launch directions, weighted the same way
        b = np.radians(compass_from(th0[r]))
        C, S_ = (w[r] * np.cos(b)).sum() / w[r].sum(), (w[r] * np.sin(b)).sum() / w[r].sum()
        arr = np.degrees(np.arctan2(S_, C)) % 360
        arr_spread = np.degrees(np.sqrt(max(0.0, -2 * np.log(max(np.hypot(C, S_), 1e-9)))))   # circular std
        out.append(dict(x=cx, y=cy, share=w[r].sum() / sum(w[q].sum() for q in runs), frm=dmean, rays=rays,
                        arr=arr, arr_spread=arr_spread))
    return out

def blocked_path(coarse, fine, frame, tab, part, view):
    """Forward ray from the view edge, heading toward the spot from the swell's direction,
    until it hits the coast."""
    T = max(part["tp"], 6.0)
    th = np.radians(270 - part["dp"])                  # travel direction (math angle)
    ux, uy = np.cos(th), np.sin(th)
    # start on the view edge, in open water, upwave of the spot, on the line that passes
    # closest to the spot (straight line toward the spot if that is open water)
    x0, x1, y0, y1 = view
    t = np.linspace(0, 1, 400)
    ex = np.concatenate([x0 + (x1 - x0) * t, np.full_like(t, x1), x0 + (x1 - x0) * t, np.full_like(t, x0)])
    ey = np.concatenate([np.full_like(t, y1), y0 + (y1 - y0) * t, np.full_like(t, y0), y0 + (y1 - y0) * t])
    la_e, lo_e = frame.lat + ey / frame.my, frame.lon + ex / frame.mx
    wet = np.array([coarse.depth_at(a, o) > 30 for a, o in zip(la_e, lo_e)])
    upwave = -(ex * ux + ey * uy) > 0
    miss = np.abs(ex * uy - ey * ux)                   # distance from the spot to the line of travel
    cand = np.flatnonzero(wet & upwave)
    if cand.size == 0:
        return np.array([0.0]), np.array([0.0]), False
    k = cand[miss[cand].argmin()]
    la0, lo0 = la_e[k], lo_e[k]
    trc, trf = Tracer(coarse, T), Tracer(fine, T)
    x, y = coarse.to_xy(la0, lo0)
    box = fine.box_in(coarse)
    xe, ye, the, st, pc = trc.trace(np.array([x]), np.array([y]), np.array([th]), keep_path=True, stop_box=box)
    segs = [_paths_to_ll(coarse, pc)[0]]
    hit = st[0] == 0
    if st[0] == 2:                                     # into the 10 m grid ...
        fx, fy = fine.to_xy(*coarse.to_ll(xe, ye))
        xf, yf, thf, stf, pf = trf.trace(fx, fy, the, ds=8.0, max_steps=3000, keep_path=True)
        segs.append(_paths_to_ll(fine, pf)[0])
        hit = stf[0] == 0
        if stf[0] == 1:                                # ... and out again: it ran past
            cx, cy = coarse.to_xy(*fine.to_ll(xf, yf))
            *_, st2, pc2 = trc.trace(cx, cy, thf, keep_path=True, max_steps=800)
            segs.append(_paths_to_ll(coarse, pc2)[0])
            hit = st2[0] == 0
    la, lo = np.concatenate([s[0] for s in segs]), np.concatenate([s[1] for s in segs])
    px, py = frame.xy(la, lo)
    px, py = resample(px, py, 40.0)
    inside = (px >= x0) & (px <= x1) & (py >= y0) & (py <= y1)
    first_out = np.flatnonzero(~inside[1:])
    if first_out.size:                                 # left the view: it runs past the spot
        px, py, hit = px[:first_out[0] + 1], py[:first_out[0] + 1], False
    return px, py, bool(hit)

def miss_point(px, py):
    """Where a blocked swell comes closest to the spot (the frame origin). The path is cut
    there, so the map shows the swell heading for the spot and missing it.
    Returns (index, distance m, compass side of the spot, ends_on_coast)."""
    d = np.hypot(px, py)
    k = int(d.argmin())
    side = compass(np.degrees(np.arctan2(px[k], py[k])) % 360)
    return k, float(d[k]), side, k >= len(px) - 3

def heights_along(x, y, frame, coarse, fine, T, h_off, h_site):
    """Display height along a centre line: offshore height in deep water, easing to the
    arriving height as the water shoals (weighted by tanh(kh), 1 in deep water)."""
    la, lo = frame.lat + y / frame.my, frame.lon + x / frame.mx
    d = np.array([(fine if fine.lat[0] < a < fine.lat[-1] and fine.lon[0] < o < fine.lon[-1] else coarse).depth_at(a, o)
                  for a, o in zip(la, lo)])
    d = np.maximum(d, 0.5)
    g = np.tanh(wavenumber(T, d) * d)
    g = np.minimum.accumulate(g)                       # monotone toward the spot
    g = np.clip((g - g[-1]) / max(g[0] - g[-1], 1e-6), 0, 1)   # 1 offshore, 0 at the spot
    return h_site + (h_off - h_site) * g

def land_polygons(grid, frame, view, tol):
    """Land as a list of shapes (each a list of rings, drawn even-odd so lakes and islands work),
    depth bands (water deeper than 20, 50 and 100 m) the same way, and 10/20/50 m contour lines."""
    X, Y = frame.xy(*np.meshgrid(grid.lat, grid.lon, indexing="ij"))
    fig, ax = plt.subplots()
    cs = ax.contourf(X, Y, grid.z, levels=[0, 1e6])
    cb = ax.contourf(X, Y, -grid.z, levels=[20, 50, 100, 1e6])
    cl = ax.contour(X, Y, -grid.z, levels=[10, 20, 50, 100])
    plt.close(fig)
    def simp(p):
        keep = [p[0]]
        for q in p[1:]:
            if np.hypot(*(q - keep[-1])) >= tol: keep.append(q)
        return np.round(np.array(keep)).astype(int).tolist()
    def shapes(paths):
        out = []
        for path in paths:
            rings = [simp(p) for p in path.to_polygons() if len(p) > 3]
            rings = [r for r in rings if len(r) > 2]
            if rings: out.append(rings)
        return out
    land = shapes(cs.get_paths())
    bands = [dict(depth=int(lev), shapes=shapes([path])) for lev, path in zip(cb.levels[:-1], cb.get_paths())]
    depth = {}
    for lev, segs in zip(cl.levels, cl.allsegs):
        depth[int(lev)] = [simp(s) for s in segs if len(s) > 3]
    return land, bands, depth

def seaward(coarse, frame):
    """Unit vector (east, north) from the spot toward open water: which way the
    coast faces, snapped to N/E/S/W. Weighted by depth on rings 2-6 km out."""
    v = np.zeros(2)
    for rad in (2000, 4000, 6000):
        for b in np.radians(np.arange(0, 360, 10)):
            x, y = rad * np.sin(b), rad * np.cos(b)
            d = coarse.depth_at(frame.lat + y / frame.my, frame.lon + x / frame.mx)
            v += np.clip(float(np.squeeze(d)), 0, 200) * np.array([np.sin(b), np.cos(b)])
    a = np.round(np.arctan2(v[0], v[1]) / (np.pi / 2)) * (np.pi / 2)
    return np.array([np.sin(a), np.cos(a)])

def coast_view(u, coarse, frame):
    """Coast map box (x0, x1, y0, y1, metres from the spot): mostly sea, a little land, north up."""
    hx, hy = VIEW_HALF if abs(u[0]) >= abs(u[1]) else VIEW_HALF[::-1]
    cx, cy = VIEW_SEAWARD * u
    gx0, gy0 = frame.xy(coarse.lat[0], coarse.lon[0]); gx1, gy1 = frame.xy(coarse.lat[-1], coarse.lon[-1])
    cx = min(max(cx, gx0 + hx), gx1 - hx); cy = min(max(cy, gy0 + hy), gy1 - hy)   # stay inside the grid
    return tuple(int(round(v)) for v in (cx - hx, cx + hx, cy - hy, cy + hy))

def shore_normal(fine, frame):
    """Compass bearing pointing straight out to sea from the spot: away from the land within
    ~900 m, each land direction counted once (the local beach and its headlands, not the
    whole coastline)."""
    v = np.zeros(2)
    for b in np.radians(np.arange(0, 360, 2)):
        for rad in (150, 300, 450, 600, 750, 900):
            x, y = rad * np.sin(b), rad * np.cos(b)
            if fine.depth_at(frame.lat + y / frame.my, frame.lon + x / frame.mx) <= 0.5:   # land
                v += np.array([np.sin(b), np.cos(b)]) / rad
                break                                            # nearest land along this bearing
    return float(np.degrees(np.arctan2(-v[0], -v[1])) % 360)

def direction_fan(tab, p, r, df):
    """How this swell's energy is spread over offshore directions, and how much of each direction
    reaches the spot, relative to the spot's most open direction at this period (1 = fully open)."""
    dirs = np.array(tab["dir_bins"], float)
    off = (r["S_off"] * p["mask"] * df).sum(0)
    site = (r["S_site"] * p["mask"] * df).sum(0)
    Wp = W_at(tab, p["tp"])
    ref = np.percentile(Wp[Wp > 0], 95) if (Wp > 0).any() else 1.0
    frac = np.where(off > 0, site / np.maximum(off, 1e-12) / ref, 0)
    keep = off >= 0.02 * off.max()
    return dict(dirs=dirs[keep].astype(int).tolist(), off=np.round(off[keep] / off.max(), 3).tolist(),
                open=np.round(np.clip(frac[keep], 0, 1), 3).tolist(),
                window=np.round(np.clip(Wp / ref, 0, 1), 2).tolist())

def forecast_series(tab, fc):
    """Breakers at the spot for each forecast hour, plus the swells making them up."""
    hours = []
    for s, parts in zip(fc["specs"], fc["parts"]):
        r = predict(s, tab, parts)
        sw = sorted(((c["hs_site"] * M2FT, c["hs_off"] * M2FT, p) for p, c in zip(parts, r["comps"])),
                    key=lambda x: -x[0])
        hours.append(dict(t=int(s["time"].timestamp()), lo=round(surf_ft(r["hb"])[0], 1), hi=round(surf_ft(r["hb"])[1], 1),
                          off=round(s["hs"] * M2FT, 1), tp=round(r["tp"]),
                          sw=[[f"{p['tp']:.0f}s {compass(p['dp'])}", round(h, 1), round(o, 1), round(p["dp"])]
                              for h, o, p in sw[:3] if o >= 0.8]))
    return dict(run=int(fc["run"].timestamp()), point=fc["point"], gain=round(fc["gain"], 2), hours=hours,
                lat=round(tab["lat"], 3), lon=round(tab["lon"], 3))

def build(tab, spec, parts, coarse, fc=None):
    fine = Bathy.fine(tab["slug"])
    frame = Frame(tab["lat"], tab["lon"])
    r = predict(spec, tab, parts)
    df = spec["df"][:, None]
    swells_out = []
    u = seaward(coarse, frame)
    COAST_VIEW = coast_view(u, coarse, frame)
    # close-up view: most of the 10 m grid, nudged seaward so the water fills most of it
    fx0, fy0 = frame.xy(fine.lat[0], fine.lon[0]); fx1, fy1 = frame.xy(fine.lat[-1], fine.lon[-1])
    span = min(float(fy1 - fy0), float(fx1 - fx0)) * 0.8
    ccx, ccy = u * span * 0.05
    cove_box = [round(max(float(fx0), ccx - span / 2)), round(min(float(fx1), ccx + span / 2)),
                round(max(float(fy0), ccy - span / 2)), round(min(float(fy1), ccy + span / 2))]
    shown = [(p, c) for p, c in zip(parts, r["comps"]) if p["tp"] >= 4 and p["hs"] * M2FT >= 1.0][:4]
    for k, (p, c) in enumerate(shown):
        p = dict(p, S=r["S_off"] * df)
        h_off, h_site = c["hs_off"] * M2FT, c["hs_site"] * M2FT
        item = dict(label=label(p), short=f"{p['tp']:.0f}s {compass(p['dp'])}", dp=round(p["dp"]),
                    tp=round(p["tp"]), off_ft=round(h_off, 1), site_ft=round(h_site, 1), color=COLORS[k],
                    blocked=bool(h_site < BLOCKED_FT), strands=[], fan=direction_fan(tab, p, r, df),
                    wavelength=round(float(2 * np.pi / wavenumber(max(p["tp"], 3.0), tab["depth"])), 1))
        frms = []
        if not item["blocked"]:
            for s in strands_for(coarse, fine, frame, tab, p, c, COAST_VIEW, ray_box=cove_box):
                if len(s["x"]) < 2:
                    continue
                share = np.sqrt(s["share"])
                h = heights_along(s["x"], s["y"], frame, coarse, fine, max(p["tp"], 6), h_off * share, h_site * share)
                item["strands"].append(dict(x=np.round(s["x"]).astype(int).tolist(), y=np.round(s["y"]).astype(int).tolist(),
                                            h=np.round(h, 2).tolist(), share=round(float(s["share"]), 2), frm=round(s["frm"]),
                                            rays=s["rays"], arr=round(float(s["arr"])), arr_spread=round(float(s["arr_spread"]), 1)))
                frms.append(s["frm"])
        # If what gets in comes from well off the swell's main direction, the main direction
        # itself is blocked: draw it too, stopping at the coast.
        off_by = min((abs((f - p["dp"] + 180) % 360 - 180) for f in frms), default=0)
        if item["strands"] and off_by > 20:
            item["edge_only"] = round(frms[0])
        if item["blocked"] or not item["strands"]:
            x, y, hit = blocked_path(coarse, fine, frame, tab, p, COAST_VIEW)
            if len(x) > 2:
                k, dist, side, at_coast = miss_point(x, y)
                k = max(k, 3)
                item["blocked_path"] = dict(x=np.round(x[:k + 1]).astype(int).tolist(),
                                            y=np.round(y[:k + 1]).astype(int).tolist(),
                                            hits_coast=bool(hit and at_coast), miss_m=round(dist), side=side)
        swells_out.append(item)
        print(f"  {item['label']:34s} {h_off:5.1f} -> {h_site:4.1f} ft, "
              f"{'blocked' if item['blocked'] else str(len(item['strands'])) + ' strand(s)'}", flush=True)
    cpoly, cband, cdepth = land_polygons(coarse, frame, COAST_VIEW, 60)
    fpoly, fband, fdepth = land_polygons(fine, frame, None, 10)
    main = max(swells_out, key=lambda s: s["site_ft"], default=None)
    return dict(spot=tab["name"], slug=tab["slug"], depth=round(tab["depth"], 1),
                time=spec["time"].strftime("%b %-d, %-I:%M %p UTC"), buoy=spec["stn"],
                buoy_label=f"NOAA buoy {spec['stn'][5:]}" if spec["stn"].startswith("ndbc:") else f"CDIP buoy {spec['stn']}",
                dir_bins=tab["dir_bins"], shore_normal=round(shore_normal(fine, frame)),
                breakers=[round(v) for v in surf_ft(r["hb"])],
                hs_ft=round(r["hs"] * M2FT, 1), main=swells_out.index(main) if main else None,
                views=dict(coast=dict(box=COAST_VIEW, land=cpoly, bands=cband, depth=cdepth),
                           cove=dict(box=cove_box, land=fpoly, bands=fband, depth=fdepth,
                                     extent=[round(float(fx0)), round(float(fx1)), round(float(fy0)), round(float(fy1))])),
                swells=swells_out, forecast=forecast_series(tab, fc) if fc else None)

if __name__ == "__main__":
    args = sys.argv[1:]
    when = None
    if "--at" in args:                                 # e.g. --at "2026-11-07 06:00" (UTC)
        i = args.index("--at"); when = dt.datetime.fromisoformat(args[i + 1]).replace(tzinfo=dt.timezone.utc); del args[i:i + 2]
    if "--hours-ago" in args:                          # e.g. --hours-ago 24 to replay yesterday
        i = args.index("--hours-ago")
        when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=float(args[i + 1])); del args[i:i + 2]
    slugs = [a for a in args if not a.startswith("--")]
    spots = [s for s in config.load_spots(kind="spot") if not slugs or s["slug"] in slugs]
    tpl = open(os.path.join(config.HERE, "ribbons_template.html")).read()
    for region in dict.fromkeys(s["region"] for s in spots):
        tabs = [t for t in load_tables(region) if t["slug"] in {s["slug"] for s in spots}]
        if not tabs:
            continue
        stn = config.REGIONS[region]["input_buoy"]
        spec = nearest(stn, when) if when else latest(stn); spec["stn"] = stn
        print(f"{config.REGIONS[region]['name']}: buoy {stn} at {spec['time']:%Y-%m-%d %H:%M} UTC", flush=True)
        parts = swells(spec)
        fc = None
        if "--no-forecast" not in sys.argv and not when:
            try:
                specs = forecast.load(region)
                gain = forecast.nudge(specs, spec)
                specs = [x for x in specs if x["time"] >= spec["time"] - dt.timedelta(hours=1.5)]
                fc = dict(specs=specs, parts=[swells(x) for x in specs], run=specs[0]["run"], gain=gain,
                          point=config.REGIONS[region]["forecast_point"])
                print(f"  forecast: WaveWatch III run {fc['run']:%Y-%m-%d %HZ}, {len(specs)} steps, "
                      f"scaled x{gain:.2f} to match the buoy", flush=True)
            except Exception as e:                       # the page still builds without it
                print("  forecast unavailable:", e, flush=True)
        coarse = Bathy.coarse(region)
        for tab in tabs:
            print(tab["name"], flush=True)
            data = build(tab, spec, parts, coarse, fc)
            out = os.path.join(config.OUT, f"ribbons_{tab['slug']}.html")
            open(out, "w").write(tpl.replace("/*DATA*/null", json.dumps(data, separators=(",", ":"))))
            print("  saved", os.path.relpath(out, config.HERE))
