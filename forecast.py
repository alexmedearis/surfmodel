"""Swell forecast input: NOAA's global WaveWatch III run (GFS-Wave), as full directional
spectra at buoy locations, hourly out to ~16 days. Each forecast hour is turned into the
same kind of spectrum dict as a buoy reading, so predict.py / ribbons.py can use it as is.

  python forecast.py [region]       print the forecast at the region's input point

NOAA runs the model 4 times a day (00, 06, 12, 18 UTC); each run's output appears ~5 h later
and stays on the server for ~2 days. Downloads are cached in data/forecast/.
"""
import os, re, sys, datetime as dt, numpy as np, requests
import config

BASE = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod"
CACHE = os.path.join(config.DATA, "forecast")

def _get(url, **kw):
    return requests.get(url, timeout=kw.pop("timeout", 120), **kw)

def runs():
    """Available runs, newest first, as (date 'YYYYMMDD', cycle 'HH')."""
    days = sorted(set(re.findall(r"gfs\.(\d{8})/", _get(BASE + "/").text)), reverse=True)
    out = []
    for d in days[:3]:
        for c in sorted(set(re.findall(r'href="(\d\d)/"', _get(f"{BASE}/gfs.{d}/").text)), reverse=True):
            out.append((d, c))
    return out

def _url(d, c, stn):
    return f"{BASE}/gfs.{d}/{c}/wave/station/bulls.t{c}z/gfswave.{stn}.spec"

def download(stn, run=None):
    """Path to the cached spectrum file for WW3 output point `stn` from `run` (default:
    the newest run whose station files are complete)."""
    os.makedirs(CACHE, exist_ok=True)
    for d, c in ([run] if run else runs()):
        path = os.path.join(CACHE, f"{d}{c}_{stn}.spec")
        if os.path.exists(path):
            return path
        r = _get(_url(d, c, stn), timeout=300)
        # a run still being written has short or missing files; the full file reaches day 16
        if r.status_code == 200 and r.text.count("\n20") >= 380:
            open(path, "w").write(r.text)
            return path
    raise RuntimeError(f"no complete WaveWatch III run found for {stn}")

def parse(path):
    """All forecast hours in a WW3 ASCII spectrum file, as a list of spectrum dicts:
    time, f, df, E (m²/Hz), hs, tp, dp, and S2d (nf, nd) in m²/Hz/rad on compass 'from'
    directions `dirs2d` (deg)."""
    lines = open(path).read().splitlines()
    nf, nd = map(int, lines[0].split("'")[2].split()[:2])
    vals, i = [], 1
    while len(vals) < nf + nd:
        vals += [float(v) for v in lines[i].split()]; i += 1
    f = np.array(vals[:nf])
    # WW3 lists directions the waves travel TOWARD, clockwise from north, in radians
    dirs = (np.degrees(vals[nf:nf + nd]) + 180) % 360
    order = np.argsort(dirs); dirs = dirs[order]
    dth = np.radians(360 / nd)
    edges = np.concatenate([[f[0] ** 2 / f[1]], f, [f[-1] ** 2 / f[-2]]])
    df = (edges[2:] - edges[:-2]) / 2                                     # geometric bands
    out = []
    while i < len(lines):
        if not re.match(r"\d{8} \d{6}", lines[i]):
            i += 1; continue
        t = dt.datetime.strptime(lines[i], "%Y%m%d %H%M%S").replace(tzinfo=dt.timezone.utc)
        hdr = lines[i + 1]
        i += 2
        vals = []
        while len(vals) < nf * nd:
            vals += [float(v) for v in lines[i].split()]; i += 1
        S = np.array(vals).reshape(nd, nf).T[:, order]                    # frequency varies fastest
        E = S.sum(1) * dth
        k = int(E.argmax())
        th = np.radians(dirs)
        a = np.arctan2((S[k] * np.sin(th)).sum(), (S[k] * np.cos(th)).sum())
        w = hdr.split("'")[2].split()                                     # lat-lon, depth, wind m/s, wind dir
        out.append(dict(time=t, f=f, df=df, E=E, S2d=S, dirs2d=dirs, hs=4 * np.sqrt((E * df).sum()),
                        tp=1 / f[k], dp=np.degrees(a) % 360,
                        wind=float(w[-4]) if len(w) >= 4 else np.nan, wind_dir=float(w[-3]) if len(w) >= 4 else np.nan))
    return out

def on_dirs(spec, dirs):
    """S(f, θ) [m²/Hz/rad] on compass 'from' directions `dirs` (deg), interpolated around the
    circle from the model's 10° bins."""
    src, S = spec["dirs2d"], spec["S2d"]
    step = 360 / len(src)
    x = ((np.asarray(dirs) - src[0]) % 360) / step
    j = np.floor(x).astype(int); w = x - j
    return S[:, j % len(src)] * (1 - w) + S[:, (j + 1) % len(src)] * w

def load(region, run=None, every=3, days=7):
    """Forecast spectra for a region's input point, every `every` hours out to `days` days."""
    stn = config.REGIONS[region]["forecast_point"]
    specs = parse(download(stn, run))
    t0 = specs[0]["time"]
    keep = [s for s in specs if (s["time"] - t0).total_seconds() % (every * 3600) == 0
            and (s["time"] - t0).total_seconds() <= days * 86400]
    for s in keep:
        s["stn"] = f"ww3:{stn}"; s["run"] = t0
    return keep

def nudge(specs, obs, tau_h=24.0):
    """Scale the forecast to agree with the latest buoy reading `obs` (a spectrum dict with
    time and hs), with the correction fading out over ~`tau_h` hours. WaveWatch III is often
    20-30% off in the size of a given swell; the buoy tells us by how much, today.
    Returns the gain applied at the buoy's time (1 = no change)."""
    t = np.array([s["time"].timestamp() for s in specs])
    t_obs = obs["time"].timestamp()
    if not t[0] - 3 * 3600 <= t_obs <= t[-1]:
        return 1.0
    hs_f = np.interp(t_obs, t, [s["hs"] for s in specs])
    gain = float(np.clip(obs["hs"] / hs_f, 0.5, 2.0))
    for s in specs:
        g = gain ** np.exp(-max(s["time"].timestamp() - t_obs, 0) / 3600 / tau_h)
        s["S2d"] = s["S2d"] * g ** 2; s["E"] = s["E"] * g ** 2; s["hs"] = s["hs"] * g
    return gain

if __name__ == "__main__":
    from partition import partition, label
    region = sys.argv[1] if len(sys.argv) > 1 else "bayarea"
    specs = load(region, every=12)
    print(f"WaveWatch III run {specs[0]['run']:%Y-%m-%d %HZ} at {config.REGIONS[region]['forecast_point']}")
    dirs = np.arange(0, 360, 5.0)
    for s in specs:
        parts = partition(on_dirs(s, dirs), s["f"], dirs, s["df"], np.radians(5))
        top = ", ".join(f"{label(p)} {p['hs'] * 3.281:.1f} ft" for p in parts[:3])
        print(f"{s['time']:%a %d %HZ}  Hs {s['hs'] * 3.281:4.1f} ft  wind {s['wind']:4.1f} m/s from {s['wind_dir']:3.0f}°  | {top}")
