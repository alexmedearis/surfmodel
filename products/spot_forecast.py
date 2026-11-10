"""The 7-day forecast at a spot: surf height for each forecast hour, plus the swells making it up."""
from predict import predict, M2FT, surf_ft
from partition import compass
from . import SCHEMA_VERSION

def spot_forecast(tab, fc):
    """`fc`: dict(specs, parts, run, gain, point) for the region (see forecast.load / nudge)."""
    hours = []
    for s, parts in zip(fc["specs"], fc["parts"]):
        r = predict(s, tab, parts)
        sw = sorted(((c["hs_site"] * M2FT, c["hs_off"] * M2FT, p) for p, c in zip(parts, r["comps"])),
                    key=lambda x: -x[0])
        lo, hi = surf_ft(r["hb"], tab["slug"])
        hours.append(dict(t=int(s["time"].timestamp()), lo=round(lo, 1), hi=round(hi, 1),
                          off=round(s["hs"] * M2FT, 1), tp=round(r["tp"]),
                          sw=[[f"{p['tp']:.0f}s {compass(p['dp'])}", round(h, 1), round(o, 1), round(p["dp"])]
                              for h, o, p in sw[:3] if o >= 0.8]))
    return dict(schema_version=SCHEMA_VERSION, slug=tab["slug"],
                run=int(fc["run"].timestamp()), point=fc["point"], gain=round(fc["gain"], 2), hours=hours,
                lat=round(tab["lat"], 3), lon=round(tab["lon"], 3))
