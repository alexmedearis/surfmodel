"""Fit a per-spot surf-height correction from logged sessions (sessions.py), and check the
model's peel direction against what people saw.

  python calibrate.py              report and write data/calibration.json
  python calibrate.py --recompute  first redo each session's prediction with the current model
                                   (where the buoy reading is still online), e.g. after a model change

The reported size is the sets, so it's compared with the top of the predicted range. The
correction is the geometric mean of reported / predicted, shrunk toward 1 when there are
few sessions (factor = exp(mean log ratio * n / (n + K))): one session moves it a little,
thirty move it almost all the way. predict.surf_ft() applies it everywhere.
"""
import json, os, sys, datetime as dt, numpy as np
import config, sessions

OUT = os.environ.get("SURF_CALIBRATION", os.path.join(config.DATA, "calibration.json"))
K = 8                    # sessions' worth of trust in the uncalibrated model
MIN_SESSIONS = 3         # below this, don't correct at all

def fit(rows):
    r = np.array([float(x["face_ft"]) / float(x["pred_surf_hi_ft"]) for x in rows])
    lr = np.log(r); n = len(r)
    sd = float(lr.std(ddof=1)) if n > 1 else float("nan")
    return dict(n=n, raw_ratio=round(float(np.exp(lr.mean())), 3),
                factor=round(float(np.exp(lr.mean() * n / (n + K))), 3) if n >= MIN_SESSIONS else 1.0,
                spread=round(sd, 3) if np.isfinite(sd) else None,
                ratio_range=[round(float(np.exp(lr.mean() - 2 * sd / np.sqrt(n))), 2),
                             round(float(np.exp(lr.mean() + 2 * sd / np.sqrt(n))), 2)] if n > 2 else None)

def main():
    rows = sessions.load()
    if "--recompute" in sys.argv:
        for x in rows:
            try:
                x.update(sessions.predict_at(x["spot"], dt.datetime.strptime(x["time"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)))
            except Exception as e:
                print(f"  {x['spot']} {x['time']}: kept old prediction ({e})")
        sessions.save_all(rows)
    usable = [x for x in rows if x.get("pred_surf_hi_ft") and float(x["pred_surf_hi_ft"]) > 0]
    print(f"{len(rows)} sessions, {len(usable)} with a model prediction\n")
    out = dict(updated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), K=K, spots={})
    print(f"{'spot':16s}{'n':>4s}{'reported/model':>16s}{'95% range':>14s}{'factor used':>13s}   peel agrees")
    for slug in sorted({x["spot"] for x in usable}):
        S = [x for x in usable if x["spot"] == slug]
        f = fit(S)
        # by period: long-period groundswell often reads differently from short-period swell
        by = {}
        for name, sel in (("under 12s", lambda x: float(x["pred_tp"]) < 12), ("12s+", lambda x: float(x["pred_tp"]) >= 12)):
            g = [x for x in S if sel(x)]
            if len(g) >= 3:
                by[name] = fit(g)["raw_ratio"]
        if by:
            f["by_period"] = by
        pe = [x for x in S if x.get("peel") in ("right", "left") and x.get("pred_peel") in ("right", "left")]
        f["peel_checked"], f["peel_agree"] = len(pe), sum(x["peel"] == x["pred_peel"] for x in pe)
        out["spots"][slug] = f
        rng = f"{f['ratio_range'][0]}-{f['ratio_range'][1]}" if f["ratio_range"] else "-"
        peel = f"{f['peel_agree']}/{f['peel_checked']}" if f["peel_checked"] else "-"
        print(f"{slug:16s}{f['n']:4d}{f['raw_ratio']:16.2f}{rng:>14s}{f['factor']:13.2f}   {peel}"
              + (f"   by period: {by}" if by else ""))
    if not usable:
        print("(nothing to fit yet)")
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"\nsaved {os.path.relpath(OUT, config.HERE)}; rebuild pages (python ribbons.py) to use it")

if __name__ == "__main__":
    main()
