"""Wind, tide and the surf rating at a spot, hour by hour for the next 7 days. Rebuilt every hour
(the wind forecast updates hourly), using the latest swell forecast for the rating."""
import numpy as np
from weather import tide_at
from . import SCHEMA_VERSION
from .insights import wind_state, rating

DAYS = 7

def _forecast_at(fc_hours, t):
    """Swell forecast (lo, hi, tp) at unix time t, interpolated between forecast steps; None outside."""
    ts = [h["t"] for h in fc_hours]
    if not ts or t < ts[0] - 5400 or t > ts[-1] + 5400:
        return None
    lo = float(np.interp(t, ts, [h["lo"] for h in fc_hours]))
    hi = float(np.interp(t, ts, [h["hi"] for h in fc_hours]))
    tp = fc_hours[min(range(len(ts)), key=lambda k: abs(ts[k] - t))]["tp"]
    return lo, hi, tp

def spot_weather(tab, wind, tide, shore_normal, forecast=None):
    """`wind`, `tide`: from weather.py (either may be None); `forecast`: the spot_forecast product."""
    out = dict(schema_version=SCHEMA_VERSION, slug=tab["slug"], shore_normal=shore_normal, wind=None, tide=None, rating=[])
    t0 = wind["hours"][0][0] if wind and wind["hours"] else None
    if wind:
        hours = []
        for t, kt, gust, d in wind["hours"][:DAYS * 24]:
            w = wind_state(kt, gust, d, shore_normal)
            hours.append([t, w["kt"], w["gust_kt"], w["dir"], w["rel"], w["score"]])
            f = _forecast_at(forecast["hours"], t) if forecast else None
            if f:
                out["rating"].append([t, rating(f[0], f[1], f[2], w)["score"]])
        out["wind"] = dict(source=wind["source"], updated=wind["updated"], hours=hours)
    if tide:
        import time
        start = t0 or int(time.time() // 3600 * 3600)
        ts = np.arange(start, start + DAYS * 86400 + 1, 3600)
        ev = [e for e in tide["events"] if start - 86400 <= e[0] <= start + (DAYS + 1) * 86400]
        out["tide"] = dict(source=tide["source"], station=tide["station"], datum=tide["datum"], events=ev,
                           hours=[[int(t), round(float(h), 2)] for t, h in zip(ts, tide_at(tide["events"], ts))])
    return out
