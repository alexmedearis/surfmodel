"""Short facts about a spot and its conditions, computed here so every client (the website, the
spot list, later the iPhone app) shows the same thing without redoing the reasoning.

  spot_facts(tab)            what the spot is open to (its swell window); goes in map.json
  conditions(now, lineup)    what today's swells do there: main swell, angle, favors lefts or
                             rights, how it peels; goes in now.json as "insights"
  wind_state, tide_state     the wind relative to the beach (offshore, onshore...) and the tide
  rating(...)                one 0-5 surf rating from size, period and wind

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

# ---------- wind, tide, rating ----------

def wind_state(speed_kt, gust_kt, wind_from, shore_normal):
    """The wind as surfers describe it. `shore_normal`: the direction the beach faces out to sea, so
    wind from there blows straight onshore and wind from the opposite way straight offshore."""
    a = abs(_rel(wind_from, shore_normal))          # 0 = straight onshore, 180 = straight offshore
    rel = ("offshore" if a >= 135 else "cross-offshore" if a >= 100 else "cross-shore" if a >= 80
           else "cross-onshore" if a >= 45 else "onshore")
    strength = "calm" if speed_kt < 4 else "light" if speed_kt < 8 else "moderate" if speed_kt < 15 else "strong"
    return dict(kt=round(speed_kt), gust_kt=round(gust_kt), dir=round(wind_from), compass=compass(wind_from),
                rel=rel, strength=strength, glassy=bool(speed_kt < 4), score=round(wind_score(speed_kt, rel), 2))

_WIND = {                    # how clean the surface stays: light, moderate, strong wind (1 = clean)
    "offshore":       (1.0, 0.9, 0.6),           # strong offshore holds waves up and blows spray back
    "cross-offshore": (0.95, 0.75, 0.45),
    "cross-shore":    (0.8, 0.45, 0.2),
    "cross-onshore":  (0.7, 0.25, 0.1),
    "onshore":        (0.6, 0.15, 0.05),
}

def wind_score(speed_kt, rel):
    if speed_kt < 4:
        return 1.0                                   # glassy, whatever the direction
    light, moderate, strong = _WIND[rel]
    if speed_kt < 8:
        return light
    if speed_kt < 15:
        return light + (moderate - light) * (speed_kt - 8) / 7
    return max(0.0, strong - 0.03 * (speed_kt - 15))

def tide_state(events, t, tide_at):
    """Height now, rising or falling, and the next high and low. `events`: [[t, ft, "H"|"L"]]."""
    h, h2 = (float(x) for x in tide_at(events, [t, t + 600]))
    nxt = [e for e in events if e[0] > t]
    out = dict(ft=round(h, 1), rising=bool(h2 > h))
    for kind, key in (("H", "next_high"), ("L", "next_low")):
        e = next((e for e in nxt if e[2] == kind), None)
        if e:
            out[key] = dict(t=e[0], ft=round(e[1], 1))
    return out

def size_score(face_ft):
    """How much surf there is to ride, by typical face height (ft): 0 flat .. 1 plenty."""
    pts = [(0, 0), (1, 0.05), (2, 0.3), (3, 0.55), (4, 0.75), (6, 0.95), (10, 1.0), (15, 0.95), (25, 0.85)]
    return float(np.interp(face_ft, *zip(*pts)))

def period_score(tp):
    return float(np.interp(tp, [5, 8, 11, 14], [0.55, 0.75, 0.9, 1.0]))

RATING_WORDS = ["flat", "poor", "poor to fair", "fair", "good", "very good", "epic"]

def rating(lo_ft, hi_ft, tp, wind=None):
    """One surf rating, 0-5 in half steps, from size, period and wind (no wind data: rated as light
    cross-shore). Tide isn't in it yet: which tide a spot likes needs session reports to learn."""
    size = size_score((lo_ft + hi_ft) / 2)
    w = wind["score"] if wind else 0.8
    r = 5 * size * (0.2 + 0.8 * w) * (0.7 + 0.3 * period_score(tp))
    r = round(r * 2) / 2
    word = RATING_WORDS[0] if size < 0.1 else RATING_WORDS[min(6, 1 + int(r // 1))] if r < 5 else RATING_WORDS[6]
    return dict(score=r, word=word)
