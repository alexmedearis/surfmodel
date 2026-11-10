"""Conditions at a spot for one buoy reading: surf height, and each swell with its path on the
map (strands), its spread of directions (fan), and how it misses the spot if it does."""
import numpy as np
from common import wavenumber
from predict import predict, W_at, M2FT, surf_ft, calibration
from partition import label, compass
from . import SCHEMA_VERSION
from .geometry import Frame, views, strands_for, heights_along, blocked_path, miss_point

COLORS = ["#1D9E75", "#D85A30", "#7F77DD", "#BA7517", "#D4537E"]
BLOCKED_FT = 0.5                                  # less than this arriving -> "blocked"

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

def swell_item(k, p, c, r, tab, coarse, fine, frame, V, df):
    """One swell as shown on the page."""
    p = dict(p, S=r["S_off"] * df)
    h_off, h_site = c["hs_off"] * M2FT, c["hs_site"] * M2FT
    item = dict(label=label(p), short=f"{p['tp']:.0f}s {compass(p['dp'])}", dp=round(p["dp"]),
                tp=round(p["tp"]), off_ft=round(h_off, 1), site_ft=round(h_site, 1), color=COLORS[k],
                blocked=bool(h_site < BLOCKED_FT), strands=[], fan=direction_fan(tab, p, r, df),
                wavelength=round(float(2 * np.pi / wavenumber(max(p["tp"], 3.0), tab["depth"])), 1))
    frms = []
    if not item["blocked"]:
        for s in strands_for(coarse, fine, frame, tab, p, c, V["coast"], ray_box=V["cove"]):
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
        x, y, hit = blocked_path(coarse, fine, frame, tab, p, V["coast"])
        if len(x) > 2:
            j, dist, side, at_coast = miss_point(x, y)
            j = max(j, 3)
            item["blocked_path"] = dict(x=np.round(x[:j + 1]).astype(int).tolist(),
                                        y=np.round(y[:j + 1]).astype(int).tolist(),
                                        hits_coast=bool(hit and at_coast), miss_m=round(dist), side=side)
    print(f"  {item['label']:34s} {h_off:5.1f} -> {h_site:4.1f} ft, "
          f"{'blocked' if item['blocked'] else str(len(item['strands'])) + ' strand(s)'}", flush=True)
    return item

def spot_now(tab, spec, parts, coarse, fine):
    """`spec`: the input buoy's spectrum (with "stn"); `parts`: its swells (predict.swells)."""
    frame = Frame(tab["lat"], tab["lon"])
    V = views(tab, coarse, fine, frame)
    r = predict(spec, tab, parts)
    df = spec["df"][:, None]
    shown = [(p, c) for p, c in zip(parts, r["comps"]) if p["tp"] >= 4 and p["hs"] * M2FT >= 1.0][:4]
    swells = [swell_item(k, p, c, r, tab, coarse, fine, frame, V, df) for k, (p, c) in enumerate(shown)]
    main = max(swells, key=lambda s: s["site_ft"], default=None)
    stn = spec["stn"]
    return dict(schema_version=SCHEMA_VERSION, slug=tab["slug"],
                time=spec["time"].strftime("%b %-d, %-I:%M %p UTC"), buoy=stn,
                buoy_label=f"NOAA buoy {stn[5:]}" if stn.startswith("ndbc:") else f"CDIP buoy {stn}",
                breakers=[round(v) for v in surf_ft(r["hb"], tab["slug"])], calibration=calibration(tab["slug"]),
                hs_ft=round(r["hs"] * M2FT, 1), main=swells.index(main) if main else None, swells=swells)
