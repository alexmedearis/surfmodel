"""Surf session reports ("how was it?"): the ground truth for calibrating surf height and peel.

This module is the shared core, meant to be reused as-is by a future web app / iPhone app
backend: the schema, the size scale, storage, and "what did the model predict for this spot at
this time". log_session.py (command line) and calibrate.py are thin wrappers around it.

One report = one row in data/sessions/sessions.csv (kept out of git: it says where and when
you surf). Every report stores the model's prediction made when it was logged, so calibration
never depends on old buoy data still being online (NOAA's realtime files only go back ~45 days).
"""
import csv, os, re, uuid, subprocess, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np
import config

PATH = os.environ.get("SURF_SESSIONS", os.path.join(config.DATA, "sessions", "sessions.csv"))
LOCAL = ZoneInfo("America/Los_Angeles")

# Face height of the set waves, in feet, for an average-height surfer (about 5'9").
# Body references are what people judge consistently; "feet" varies a lot between surfers.
SIZES = {
    "ankle": 1.0, "knee": 2.0, "thigh": 2.5, "waist": 3.0, "stomach": 3.5, "chest": 4.0,
    "shoulder": 4.5, "head": 5.5, "overhead": 7.0, "well-overhead": 9.0,
    "double-overhead": 11.0, "triple-overhead": 16.0,
}
PEELS = ("right", "left", "both", "closeout", "none")

FIELDS = [
    # what the surfer reported
    "id", "logged_at", "user", "source", "spot", "time", "size", "face_ft", "peel", "quality", "note",
    # what the model predicted for that spot and time, when the report was logged (uncalibrated)
    "model_version", "buoy", "buoy_time", "pred_hs_ft", "pred_tp", "pred_hb_m", "pred_surf_lo_ft",
    "pred_surf_hi_ft", "pred_main", "pred_peel", "pred_peel_angle",
]

def face_ft(size):
    """Set face height (ft) from a body reference ('head', 'chest', ...) or a number of feet."""
    s = str(size).strip().lower().replace(" ", "-").replace("_", "-")
    s = {"head-high": "head", "overhead+": "well-overhead", "double": "double-overhead",
         "triple": "triple-overhead", "doh": "double-overhead", "toh": "triple-overhead"}.get(s, s)
    if s in SIZES:
        return SIZES[s]
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(ft|feet|')?", s)
    if m:
        return float(m.group(1))
    raise ValueError(f"size {size!r}: use one of {', '.join(SIZES)} or a number of feet")

def parse_time(text, utc=False):
    """'2026-11-09 07:30', '07:30', '7:30am', 'yesterday 4pm' (local California time unless utc)."""
    tz = dt.timezone.utc if utc else LOCAL
    now = dt.datetime.now(tz)
    t = text.strip().lower()
    day = now.date()
    if t.startswith("yesterday"):
        day = day - dt.timedelta(days=1); t = t[len("yesterday"):].strip()
    elif t.startswith("today"):
        t = t[len("today"):].strip()
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[ t](.+)", t)
    if m:
        day = dt.date.fromisoformat(m.group(1)); t = m.group(2)
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if not m:
        raise ValueError(f"time {text!r}: use e.g. '7:30am', '16:00' or '2026-11-09 07:30'")
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and h < 12:
        h += 12
    if m.group(3) == "am" and h == 12:
        h = 0
    return dt.datetime.combine(day, dt.time(h, mi), tz).astimezone(dt.timezone.utc)

def model_version():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.HERE,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""

def predict_at(slug, when, with_peel=True):
    """The model's (uncalibrated) prediction for spot `slug` at UTC datetime `when`, from the
    region's input buoy reading nearest that time."""
    from buoy import nearest
    from predict import load_tables, predict, swells, M2FT, SURF_RANGE
    spot = next(s for s in config.load_spots(kind="spot") if s["slug"] == slug)
    tab = next(t for t in load_tables(spot["region"]) if t["slug"] == slug)
    stn = config.REGIONS[spot["region"]]["input_buoy"]
    spec = nearest(stn, when)
    if abs((spec["time"] - when).total_seconds()) > 3 * 3600:
        raise ValueError(f"no {stn} buoy reading within 3 h of {when:%Y-%m-%d %H:%M} UTC")
    parts = swells(spec)
    r = predict(spec, tab, parts)
    main = max(zip(parts, r["comps"]), key=lambda pc: pc[1]["hs_site"], default=(None, None))
    out = dict(model_version=model_version(), buoy=stn, buoy_time=spec["time"].strftime("%Y-%m-%dT%H:%MZ"),
               pred_hs_ft=round(r["hs"] * M2FT, 2), pred_tp=round(float(r["tp"]), 1), pred_hb_m=round(float(r["hb"]), 3),
               pred_surf_lo_ft=round(r["hb"] * M2FT * SURF_RANGE[0], 1), pred_surf_hi_ft=round(r["hb"] * M2FT * SURF_RANGE[1], 1),
               pred_main=main[1]["label"] if main[0] else "", pred_peel="", pred_peel_angle="")
    if with_peel and main[0] is not None and spot.get("break") in ("point", "reef"):
        try:
            out.update(_peel(spot, tab, main[0], main[1]))
        except Exception:
            pass
    return out

def _peel(spot, tab, part, comp):
    """Which way the model says the main swell peels at the spot (point and reef breaks)."""
    import lineup
    from common import Bathy
    fine = Bathy.fine(spot["slug"])
    F = lineup.wavefield(Bathy.coarse(spot["region"]), fine, tab["lat"], tab["lon"], max(part["tp"], 5), part["dp"])
    if F is None:
        return {}
    segs = [g for g in lineup.peel(F, comp["hs_off"]) if np.hypot(np.diff(g["x"]), np.diff(g["y"])).sum() >= 40]
    if not segs:
        return dict(pred_peel="none")
    sx, sy = fine.to_xy(spot["lat"], spot["lon"]); sx -= F["x0"]; sy -= F["y0"]
    g = min(segs, key=lambda g: np.min(np.hypot(np.array(g["x"]) - sx, np.array(g["y"]) - sy)))
    return dict(pred_peel="right" if g["right"] else "left", pred_peel_angle=round(float(np.median(g["angle"]))))

def load(path=PATH):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))

def save_all(rows, path=PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS, extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def add(spot, when, size, peel="", quality="", note="", user="me", source="cli", path=PATH, with_peel=True):
    """Record a report (and the model's prediction for it). Returns the stored row."""
    spots = {s["slug"] for s in config.load_spots(kind="spot")}
    if spot not in spots:
        raise ValueError(f"unknown spot {spot!r}: one of {', '.join(sorted(spots))}")
    if peel and peel not in PEELS:
        raise ValueError(f"peel {peel!r}: one of {', '.join(PEELS)}")
    if quality and not (str(quality).isdigit() and 1 <= int(quality) <= 5):
        raise ValueError("quality: 1 (poor) to 5 (epic)")
    row = dict(id=uuid.uuid4().hex[:10], logged_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
               user=user, source=source, spot=spot, time=when.strftime("%Y-%m-%dT%H:%MZ"), size=size,
               face_ft=face_ft(size), peel=peel, quality=quality, note=note)
    try:
        row.update(predict_at(spot, when, with_peel))
    except Exception as e:                          # keep the report; calibrate.py --recompute can fill it in
        row["note"] = (note + " " if note else "") + f"[no prediction: {e}]"
    rows = load(path); rows.append(row); save_all(rows, path)
    return row
