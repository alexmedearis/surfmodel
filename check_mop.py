"""Check each spot's 10 m grid against CDIP's MOP nearshore model, which gives hourly wave
height every ~100 m along the California coast at 10-15 m depth (computed independently,
with a different method and bathymetry). There are no buoys at the breaks; this is the best
available check of the spot-level part of the model.

  python check_mop.py [slug ...] [--days 30]

For each spot with a `mop` point in spots.csv: ray-traces a transfer table at that exact point
(cached in data/tables/mop_<slug>.json), drives it with the region's input buoy, and compares
with MOP's nowcast. Writes out/check_mop.png.
"""
import json, os, re, sys, time, numpy as np, requests, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config, buoy
from common import Bathy
from predict import predict, M2FT
from raytrace import transfer_table, PERIODS, DIR_BINS

MOP = "https://thredds.cdip.ucsd.edu/thredds/dodsC/cdip/model/MOP_alongshore/{}_nowcast.nc"

def mop_meta(pid):
    keys = ["metaLatitude", "metaLongitude", "metaWaterDepth", "metaShoreNormal"]
    txt = requests.get(MOP.format(pid) + ".ascii?" + ",".join(keys), timeout=60).text
    return {k: float(re.search(k + r", ([-\d.]+)", txt).group(1)) for k in keys}

def mop_history(pid, days):
    t = buoy._ascii(MOP.format(pid), "waveTime")["waveTime"]
    n, i0 = len(t), int(np.searchsorted(t, t[-1] - days * 86400))
    r = f"[{i0}:1:{n - 1}]"
    return buoy._ascii(MOP.format(pid), f"waveTime{r},waveHs{r}")

def table_at_mop(spot, meta):
    path = os.path.join(config.DATA, "tables", f"mop_{spot['slug']}.json")
    if os.path.exists(path):
        t = json.load(open(path)); t["W"] = np.array(t["W"]); return t
    t0 = time.time()
    coarse, fine = Bathy.coarse(spot["region"]), Bathy.fine(spot["slug"])
    la, lo, h = fine.site_point(meta["metaLatitude"], meta["metaLongitude"], meta["metaWaterDepth"], radius_km=0.4)
    W = transfer_table(coarse, la, lo, h, fine=fine)
    t = dict(slug=f"mop_{spot['slug']}", name=spot["name"], lat=float(la), lon=float(lo), depth=float(h),
             periods=PERIODS, dir_bins=DIR_BINS.tolist(), W=W.tolist())
    json.dump(t, open(path, "w"))
    print(f"  traced a table at {spot['mop']} ({h:.1f} m deep) in {time.time() - t0:.0f}s", flush=True)
    t["W"] = W
    return t

def main():
    args = sys.argv[1:]
    days = 30
    if "--days" in args:
        i = args.index("--days"); days = float(args[i + 1]); del args[i:i + 2]
    spots = [s for s in config.load_spots(kind="spot") if s.get("mop") and (not args or s["slug"] in args)]
    hist, rows = {}, []
    fig, axs = plt.subplots(len(spots), 1, figsize=(11, 2.3 * len(spots)), sharex=True, squeeze=False)
    for ax, s in zip(axs[:, 0], spots):
        meta = mop_meta(s["mop"])
        print(f"{s['name']}: MOP {s['mop']} ({meta['metaWaterDepth']:.0f} m deep)", flush=True)
        tab = table_at_mop(s, meta)
        stn = config.REGIONS[s["region"]]["input_buoy"]
        if stn not in hist:
            hist[stn] = buoy.history(stn, days + 1)
        h, d = hist[stn], mop_history(s["mop"], days)
        j = np.clip(np.searchsorted(h["time"], d["waveTime"]), 1, len(h["time"]) - 1)
        j = np.where(np.abs(h["time"][j - 1] - d["waveTime"]) < np.abs(h["time"][j] - d["waveTime"]), j - 1, j)
        ok = (np.abs(h["time"][j] - d["waveTime"]) <= 1200) & np.isfinite(d["waveHs"]) & (d["waveHs"] > 0)
        ours = np.array([predict(buoy.at(h, i), tab)["hs"] for i in j[ok]])
        mop, off = d["waveHs"][ok], h["hs"][j[ok]]
        e = (ours - mop) * M2FT
        rows.append((s["name"], s["mop"], ok.sum(), np.median(ours / mop), np.sqrt((e ** 2).mean()), e.mean(),
                     np.corrcoef(ours, mop)[0, 1], np.median(mop / off), np.median(ours / off)))
        t = d["waveTime"][ok].astype("datetime64[s]")
        ax.plot(t, off * M2FT, color="0.7", lw=0.8, label="offshore buoy")
        ax.plot(t, mop * M2FT, "k", lw=1.1, label=f"CDIP MOP {s['mop']}")
        ax.plot(t, ours * M2FT, color="#d9480f", lw=1, label="this model")
        ax.set_title(f"{s['name']}: ours/MOP {rows[-1][3]:.2f}, r {rows[-1][6]:.2f}", fontsize=10, loc="left")
        ax.set_ylabel("Hs (ft)"); ax.grid(alpha=0.3)
    axs[0, 0].legend(fontsize=8, loc="upper right")
    fig.autofmt_xdate(); fig.tight_layout()
    out = os.path.join(config.OUT, "check_mop.png"); fig.savefig(out, dpi=120)
    print(f"\nWave height at the MOP point, last {days:.0f} days (ft)")
    print(f"{'':16s}{'MOP':7s}{'n':>5s}{'ours/MOP':>10s}{'RMSE':>6s}{'bias':>6s}{'r':>6s}   share of offshore height: MOP / ours")
    for n, p, k, ratio, rmse, bias, r, fm, fo in rows:
        print(f"{n:16s}{p:7s}{k:5d}{ratio:10.2f}{rmse:6.1f}{bias:+6.1f}{r:6.2f}   {fm:.2f} / {fo:.2f}")
    print("saved", os.path.relpath(out, config.HERE))

if __name__ == "__main__":
    main()
