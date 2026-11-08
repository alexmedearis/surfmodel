"""Check the model against nearshore buoys: predict what each check buoy (kind=buoy in
spots.csv) should read from the region's deep-water input buoy, and compare.

  python validate.py [region] [days] [--compare-coarse]

--compare-coarse also traces a 90 m-only table on the fly, to see what the ~10 m grid adds.
Writes out/check_<slug>.png.
"""
import sys, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config, buoy
from common import Bathy
from predict import load_tables, predict, M2FT
from raytrace import transfer_table

def stats(pred, obs):
    bias = (pred - obs).mean()
    return dict(bias=bias, rmse=np.sqrt(((pred - obs) ** 2).mean()), r=np.corrcoef(pred, obs)[0, 1],
                ratio=np.median(pred / obs), si=np.sqrt(((pred - obs - bias) ** 2).mean()) / obs.mean())

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    region = args[0] if args else "bayarea"
    days = float(args[1]) if len(args) > 1 else 30
    stn_in = config.REGIONS[region]["input_buoy"]
    name_in = f"NOAA {stn_in[5:]}" if stn_in.startswith("ndbc:") else f"CDIP {stn_in}"
    hin = buoy.history(stn_in, days)
    for tab in load_tables(region, kind="buoy"):
        hck = buoy.history(tab["station"], days)
        tables = [("10 m nearshore grid", tab)]
        if "--compare-coarse" in sys.argv:
            coarse = Bathy.coarse(region)
            sla, slo, sh = coarse.site_point(tab["lat"], tab["lon"], None)
            ctab = dict(tab, W=transfer_table(coarse, sla, slo, sh), depth=float(sh))
            tables.append(("90 m grid only", ctab))
        # pair each check-buoy record with the input record nearest in time (within 20 min)
        j = np.clip(np.searchsorted(hin["time"], hck["time"]), 1, len(hin["time"]) - 1)
        j = np.where(np.abs(hin["time"][j - 1] - hck["time"]) < np.abs(hin["time"][j] - hck["time"]), j - 1, j)
        ok = np.abs(hin["time"][j] - hck["time"]) <= 1200
        obs = hck["hs"][ok]
        t = hck["time"][ok].astype("datetime64[s]")
        print(f"{tab['name']} (CDIP {tab['station']}) vs model driven by {name_in}: {ok.sum()} records, last {days:.0f} days")
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(t, obs * M2FT, "k", lw=1.2, label=f"measured (CDIP {tab['station']})")
        ax.plot(t, hin["hs"][j[ok]] * M2FT, color="0.6", lw=0.8, label=f"offshore input ({name_in})")
        for (name, tb), col in zip(tables, ("#d9480f", "#1c7ed6")):
            pred = np.array([predict(buoy.at(hin, i), tb)["hs"] for i in j[ok]])
            s = stats(pred, obs)
            print(f"  {name:20s} bias {s['bias']*M2FT:+.1f} ft  RMSE {s['rmse']*M2FT:.1f} ft  "
                  f"scatter {s['si']:.0%}  r {s['r']:.2f}  median pred/obs {s['ratio']:.2f}")
            ax.plot(t, pred * M2FT, color=col, lw=1, label=f"model, {name} (bias {s['bias']*M2FT:+.1f} ft, r {s['r']:.2f})")
        s0 = stats(hin["hs"][j[ok]], obs)
        print(f"  {'(offshore as-is)':20s} bias {s0['bias']*M2FT:+.1f} ft  RMSE {s0['rmse']*M2FT:.1f} ft  r {s0['r']:.2f}")
        ax.set_ylabel("Hs (ft)"); ax.legend(fontsize=8, loc="upper left"); ax.grid(alpha=0.3)
        ax.set_title(f"Model check: {tab['name']}, last {days:.0f} days")
        fig.autofmt_xdate(); fig.tight_layout()
        out = f"{config.OUT}/check_{tab['slug']}.png"
        fig.savefig(out, dpi=130); print("  saved", out.replace(config.HERE + "/", ""))

if __name__ == "__main__":
    main()
