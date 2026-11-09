"""Score the logged forecasts (forecast_log.py) against what the buoys actually measured.

  python score_forecast.py [days]      only runs from the last `days` days (default: all)

For each buoy and each forecast range (day 1, day 2, ...), compares wave height (Hs):
  WaveWatch III as-is, our forecast (scaled to the live buoy at the start), and at the check
  buoys, WaveWatch III's own output there. Spots have no buoy, so they aren't scored here.
Hours before a run was published are left out (they were already in the past).
"""
import csv, glob, os, sys, datetime as dt, numpy as np
import config

M2FT = 3.281
LEADS = [(6, 24), (24, 48), (48, 72), (72, 120), (120, 169)]   # a run comes out ~5 h after its start time

def load(pattern):
    rows = []
    for p in sorted(glob.glob(os.path.join(config.DATA, "forecast_log", pattern))):
        with open(p) as fh:
            rows += list(csv.DictReader(fh))
    return rows

def ts(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc).timestamp()

def main():
    days = float(sys.argv[1]) if len(sys.argv) > 1 else None
    fc, obs = load("forecasts_*.csv"), load("obs_*.csv")
    if not fc:
        sys.exit("no forecasts logged yet: run forecast_log.py")
    cut = (dt.datetime.now(dt.timezone.utc).timestamp() - days * 86400) if days else 0
    by_stn = {}
    for o in obs:
        by_stn.setdefault(o["station"], []).append((ts(o["time"]), float(o["hs"])))
    by_stn = {k: np.array(sorted(v)) for k, v in by_stn.items()}

    def matched(rows):
        """(lead, forecast hs_raw, forecast hs, observed) for rows with a reading within 20 min."""
        out = []
        for r in rows:
            o = by_stn.get(r["target"])
            if o is None:
                continue
            t = ts(r["time"]); i = int(np.abs(o[:, 0] - t).argmin())
            if abs(o[i, 0] - t) <= 1200:
                out.append((float(r["lead_h"]), float(r["hs_raw"]), float(r["hs"] or "nan"), o[i, 1]))
        return np.array(out).reshape(-1, 4)

    def stats(p, o):
        e = (p - o) * M2FT
        return f"{np.sqrt((e ** 2).mean()):4.1f} ({e.mean():+.1f})"

    fc = [r for r in fc if ts(r["run"]) >= cut]
    runs = sorted({r["run"] for r in fc})
    print(f"{len(runs)} runs, {runs[0]} to {runs[-1]}. Wave height error in ft: RMSE (bias)\n")
    for region, R in config.REGIONS.items():
        rr = [r for r in fc if r["region"] == region]
        if not rr:
            continue
        print(f"== {R['name']}")
        targets = [("input", R["input_buoy"])] + sorted({("check", r["target"]) for r in rr if r["kind"] == "check"})
        for kind, target in targets:
            M = matched([r for r in rr if r["kind"] == kind and r["target"] == target])
            W = matched([r for r in rr if r["kind"] == "ww3_check" and r["target"] == target]) if kind == "check" else None
            name = f"input buoy {target}" if kind == "input" else f"check buoy CDIP {target}"
            print(f"  {name}")
            hdr = "WW3 as-is" if kind == "input" else "WW3 -> our tables"
            print(f"    {'ahead':10s} {'n':>4s}   {hdr:>18s}   {'scaled to buoy':>15s}" + ("   WW3's own point" if W is not None else ""))
            for lo, hi in LEADS:
                m = (M[:, 0] >= lo) & (M[:, 0] < hi)
                if m.sum() < 5:
                    continue
                line = f"    {f'{lo}-{min(hi, 168)} h':10s} {m.sum():4d}   {stats(M[m, 1], M[m, 3]):>18s}   {stats(M[m, 2], M[m, 3]):>15s}"
                if W is not None and len(W):
                    w = (W[:, 0] >= lo) & (W[:, 0] < hi)
                    if w.sum() >= 5:
                        line += f"   {stats(W[w, 1], W[w, 3]):>15s}"
                print(line)
        print()

if __name__ == "__main__":
    main()
