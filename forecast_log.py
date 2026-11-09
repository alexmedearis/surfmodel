"""Keep a record of every forecast, so we can score it later against what the buoys measured.
NOAA only keeps ~2 days of forecast runs online, so anything not logged is gone.

  python forecast_log.py            log every run that's online and not logged yet, plus recent buoy readings

Runs every 6 hours on GitHub Actions (.github/workflows/forecast-log.yml) and commits the result.
Writes, per month, to data/forecast_log/:
  forecasts_YYYY-MM.csv   run, region, target, kind, time, lead_h, hs_raw, hs, hb
      kind = input  (the region's deep-water input buoy: WaveWatch III as-is, and scaled to the buoy)
             check  (a nearshore check buoy: our tables applied to the forecast; plus kind=ww3_check,
                     WaveWatch III's own output at that buoy, for comparison)
             spot   (a surf spot: hs at the model point, and estimated breakers hb)
      hs_raw = from the unscaled forecast, hs = after scaling to the live buoy (all in metres)
  obs_YYYY-MM.csv         station, time, hs   (buoy readings, deduplicated)
"""
import csv, os, datetime as dt, numpy as np
import config, forecast, buoy
from predict import load_tables, predict, swells

LOG = os.path.join(config.DATA, "forecast_log")
EVERY_H, DAYS = 3, 7
AVAILABLE_AFTER_H = 5            # a run's files appear ~5 h after its nominal time: scale to the buoy then
FIELDS = ["run", "region", "target", "kind", "time", "lead_h", "hs_raw", "hs", "hb"]

# WaveWatch III output points at the check buoys (CDIP station -> NDBC id)
WW3_AT_CDIP = {"142": "46237", "156": "46236"}

def iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")

def logged_runs():
    done = set()
    if os.path.isdir(LOG):
        for fn in os.listdir(LOG):
            if fn.startswith("forecasts_"):
                with open(os.path.join(LOG, fn)) as fh:
                    done |= {(r["run"], r["region"]) for r in csv.DictReader(fh)}
    return done

def append(name, fields, rows):
    os.makedirs(LOG, exist_ok=True)
    path = os.path.join(LOG, name)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fields)
        if new:
            w.writeheader()
        w.writerows(rows)

def thin(specs, t0):
    return [s for s in specs if (s["time"] - t0).total_seconds() % (EVERY_H * 3600) == 0
            and (s["time"] - t0).total_seconds() <= DAYS * 86400]

def log_run(region, run, hist):
    """Rows for one region from one run. `hist` is the input buoy's recent history."""
    R = config.REGIONS[region]
    specs = forecast.parse(forecast.download(R["forecast_point"], run))
    t0 = specs[0]["time"]
    raw = thin(specs, t0)
    scaled = [dict(s) for s in raw]
    # scale to the buoy reading at the time the run came out (not a later one: no peeking)
    t_avail = (t0 + dt.timedelta(hours=AVAILABLE_AFTER_H)).timestamp()
    i = int(np.abs(hist["time"] - t_avail).argmin())
    gain = 1.0
    if abs(hist["time"][i] - t_avail) <= 3 * 3600:
        gain = forecast.nudge(scaled, buoy.at(hist, i))
    rows = []
    def row(target, kind, s_raw, hs_raw, hs, hb=""):
        rows.append(dict(run=iso(t0), region=region, target=target, kind=kind, time=iso(s_raw["time"]),
                         lead_h=round((s_raw["time"] - t0).total_seconds() / 3600),
                         hs_raw=round(float(hs_raw), 3), hs=round(float(hs), 3) if hs != "" else "",
                         hb=round(float(hb), 3) if hb != "" else ""))
    for a, b in zip(raw, scaled):
        row(R["input_buoy"], "input", a, a["hs"], b["hs"])
    tabs = [(t, "check") for t in load_tables(region, kind="buoy")] + [(t, "spot") for t in load_tables(region)]
    parts_raw = [swells(s) for s in raw]
    for tab, kind in tabs:
        for a, b, pa in zip(raw, scaled, parts_raw):
            ra, rb = predict(a, tab, pa), predict(b, tab, pa)
            row(tab.get("station") if kind == "check" else tab["slug"], kind, a, ra["hs"], rb["hs"],
                rb["hb"] if kind == "spot" else "")
        if kind == "check" and tab.get("station") in WW3_AT_CDIP:
            own = thin(forecast.parse(forecast.download(WW3_AT_CDIP[tab["station"]], run)), t0)
            for s in own:
                row(tab["station"], "ww3_check", s, s["hs"], "")
    return t0, gain, rows

def log_obs(stations):
    have = set()
    if os.path.isdir(LOG):
        for fn in os.listdir(LOG):
            if fn.startswith("obs_"):
                with open(os.path.join(LOG, fn)) as fh:
                    have |= {(r["station"], r["time"]) for r in csv.DictReader(fh)}
    n = 0
    for stn in stations:
        h = buoy.history(stn, 3)
        by_month = {}
        for t, hs in zip(h["time"], h["hs"]):
            t = dt.datetime.fromtimestamp(float(t), dt.timezone.utc)
            if (stn, iso(t)) in have or not np.isfinite(hs):
                continue
            by_month.setdefault(t.strftime("%Y-%m"), []).append(dict(station=stn, time=iso(t), hs=round(float(hs), 3)))
        for m, rows in by_month.items():
            append(f"obs_{m}.csv", ["station", "time", "hs"], sorted(rows, key=lambda r: r["time"])); n += len(rows)
    return n

def main():
    done = logged_runs()
    regions = [r for r, R in config.REGIONS.items() if R.get("forecast_point") and load_tables(r)]
    runs = forecast.runs()
    stations = []
    for region in regions:
        R = config.REGIONS[region]
        stations += [R["input_buoy"]] + [t["station"] for t in load_tables(region, kind="buoy")]
        hist = buoy.history(R["input_buoy"], 3)
        for d, c in reversed(runs):                       # oldest first
            t0 = dt.datetime.strptime(d + c, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
            if (iso(t0), region) in done:
                continue
            try:
                t0, gain, rows = log_run(region, (d, c), hist)
            except Exception as e:                        # most often: the newest run isn't complete yet
                print(f"{region} {d} {c}Z: skipped ({e})")
                continue
            append(f"forecasts_{t0:%Y-%m}.csv", FIELDS, rows)
            print(f"{region} {d} {c}Z: logged {len(rows)} rows, scaled x{gain:.2f}")
    print(f"buoy readings: {log_obs(dict.fromkeys(stations))} new")
    # spectrum files are only a cache: keep the last few days
    for fn in os.listdir(forecast.CACHE) if os.path.isdir(forecast.CACHE) else []:
        p = os.path.join(forecast.CACHE, fn)
        if os.path.getmtime(p) < dt.datetime.now().timestamp() - 3 * 86400:
            os.remove(p)

if __name__ == "__main__":
    main()
