"""Short facts about a spot and its conditions, computed here so every client (the website, the
spot list, later the iPhone app) shows the same thing without redoing the reasoning.

  spot_facts(tab)            what the spot is open to (its swell window); goes in map.json
  conditions(now, lineup)    what today's swells do there: main swell, angle, favors lefts or
                             rights, how it peels; goes in now.json as "insights"

Plain facts and categories only; the wording stays with each client.
"""
import numpy as np
import config
from predict import W_at
from partition import compass

WINDOW_PERIODS = (10, 14, 18)          # wind swell, groundswell, long-period groundswell (s)
OPEN_FRACTION = 0.5                    # a direction is "open" if it gets this share of the best one's energy

def _runs(dirs, keep):
    """Contiguous runs of kept directions (wrapping past north) as [from, to] pairs."""
    if not keep.any():
        return []
    n = len(dirs)
    if keep.all():
        return [[0, 360]]
    start = next(i for i in range(n) if keep[i] and not keep[i - 1])   # a run's first bin
    runs, cur = [], None
    for k in range(n):
        i = (start + k) % n
        if keep[i]:
            cur = [dirs[i], dirs[i]] if cur is None else [cur[0], dirs[i]]
        elif cur:
            runs.append(cur); cur = None
    if cur:
        runs.append(cur)
    return [[int(a), int(b)] for a, b in runs]

def spot_facts(tab):
    """The swell window: for a few periods, the direction that reaches the spot best, the ranges
    of directions that are open, and how a swell from the best direction changes in height
    (height_ratio > 1: the seafloor focuses it; < 1: the spot is sheltered)."""
    key = "W_break" if "W_break" in tab else "W"
    dirs = np.array(tab["dir_bins"], float)
    out = []
    for T in WINDOW_PERIODS:
        w = W_at(tab, T, key)
        if w.max() <= 0:
            out.append(dict(period=T, best_dir=None, open=[], height_ratio=0.0))
            continue
        b = int(w.argmax())
        out.append(dict(period=T, best_dir=int(dirs[b]), best_compass=compass(dirs[b]),
                        open=_runs(dirs, w >= OPEN_FRACTION * w.max()),
                        height_ratio=round(float(np.sqrt(w.max())), 2)))
    return dict(break_type=config.break_type(tab["slug"]), window=out)

# ---------- conditions ----------

def _rel(a, b):
    """a - b as an angle in (-180, 180]."""
    return (a - b + 540) % 360 - 180

def arrival(s):
    """Share-weighted direction a swell arrives from at the spot (degrees), from its strands."""
    st = [t for t in s["strands"] if t.get("arr") is not None]
    if not st:
        return None
    c = sum(t["share"] * np.cos(np.radians(t["arr"])) for t in st)
    n = sum(t["share"] * np.sin(np.radians(t["arr"])) for t in st)
    return float(np.degrees(np.arctan2(n, c)) % 360)

def peel_class(angle):
    """Peel angle (between break line and crest) as a category: higher is slower and easier."""
    return "slow" if angle >= 60 else "makeable" if angle >= 45 else "fast" if angle >= 30 else "closeout"

def _peel(lineup, main, break_type):
    """How the main swell's bigger waves peel near the spot, from the lineup's break lines."""
    if break_type in ("beach", "jetty"):
        return dict(known=False, reason="sand")          # depends on sandbars: not in any data
    L = next((x for x in (lineup or {}).get("swells", []) if x["i"] == main), None)
    if L is None:
        return None
    segs = [p for p in L["peel"] if p["len"] >= 40]
    if not segs:
        return dict(known=True, side=None, reason="shorebreak")
    px, py = lineup["spot"]
    dist = lambda p: min(np.hypot(x - px, y - py) for x, y in zip(p["x"], p["y"]))
    near = min(segs, key=dist)
    side = lambda p: "right" if p["right"] else "left"
    out = dict(known=True, side=side(near), angle=near["angle"], cls=peel_class(near["angle"]),
               length_m=int(round(near["len"] / 10) * 10), from_spot_m=int(round(dist(near) / 10) * 10))
    other = sorted((p for p in segs if p is not near and p["right"] != near["right"] and p["len"] >= 150),
                   key=lambda p: -p["len"])
    if other:
        out["also"] = dict(side=side(other[0]), angle=other[0]["angle"], length_m=int(round(other[0]["len"] / 10) * 10))
    return out

def conditions(now, lineup=None, shore_normal=None):
    """Facts about the current swells at the spot. `now`: the now product; `lineup`: the lineup
    product (optional; gives the peel); `shore_normal`: the direction the beach faces out to."""
    live = [i for i, s in enumerate(now["swells"]) if not s["blocked"] and s["strands"] and s["site_ft"] >= 0.3]
    if not live:
        return dict(main=None, surf_ft=now["breakers"])
    m = max(live, key=lambda i: now["swells"][i]["site_ft"])
    s = now["swells"][m]
    arr = arrival(s)
    out = dict(main=m, surf_ft=now["breakers"], main_swell=dict(short=s["short"], period=s["tp"], dir=s["dp"],
               site_ft=s["site_ft"], arrives_from=round(arr), bends=round(abs(_rel(arr, s["dp"])))))
    if shore_normal is not None:
        a = _rel(arr, shore_normal)                       # + = from your left as you face the beach
        out["angle_to_beach"] = round(abs(a))
        out["favors"] = "peaks" if abs(a) < 10 else "rights" if a > 0 else "lefts"
        out["runs_along_shore"] = bool(abs(a) > 55)
    if len(s["strands"]) > 1:
        d = [t["arr"] for t in s["strands"]]
        if max(d) - min(d) > 12:
            out["routes"] = dict(n=len(d), spread=round(max(d) - min(d)))
    out["peel"] = _peel(lineup, m, config.break_type(now["slug"]))
    others = []
    for i in live:
        if i == m or now["swells"][i]["site_ft"] < 0.25 * s["site_ft"]:
            continue
        o = now["swells"][i]
        d = abs(_rel(arrival(o), arr))
        others.append(dict(i=i, effect="crossing" if d > 20 else "texture" if o["tp"] < 9 else "adds size"))
    out["others"] = others
    share = s["site_ft"] ** 2 / sum(now["swells"][i]["site_ft"] ** 2 for i in live)
    out["mix"] = ("clean groundswell" if s["tp"] >= 13 and share > 0.7 else
                  "mixed groundswell" if s["tp"] >= 13 else "short period")
    return out
