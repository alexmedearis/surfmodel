"""Wind and tide for a spot, from free US government sources (public domain, fine to use commercially):

  wind: NOAA National Weather Service gridded forecast (api.weather.gov), hourly for ~7 days
  tide: NOAA CO-OPS tide predictions (api.tidesandcurrents.noaa.gov), highs and lows, with the
        curve between them drawn the standard way (a half cosine from each high to the next low)

  python weather.py [slug]     print the wind and tide for a spot
"""
import datetime as dt, functools, math, re, sys, time
import numpy as np
import requests
import config

UA = {"User-Agent": "surfmodel/0.1", "Accept": "application/geo+json"}
KMH_TO_KT = 1 / 1.852

def _get(url, params=None, tries=3, headers=None):
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers or UA, timeout=30)
            if r.status_code == 200:
                return r.json()
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = repr(e)
        time.sleep(2 * (k + 1))                      # the weather service has the odd 500; try again
    raise RuntimeError(f"{url}: {err}")

# ---------- wind ----------

@functools.lru_cache(maxsize=None)
def _grid_url(lat, lon):
    return _get(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}")["properties"]["forecastGridData"]

@functools.lru_cache(maxsize=None)
def _grid(url, hour):                                # `hour`: cache key, so one fetch per grid cell per hour
    return _get(url)["properties"]

_DUR = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?)?")

def _hourly(series, factor=1.0):
    """NWS values like {"validTime": "2026-11-12T13:00:00+00:00/PT2H", "value": 9.3} -> {unix hour: value}."""
    out = {}
    for v in series["values"]:
        if v["value"] is None:
            continue
        start, dur = v["validTime"].split("/")
        d, h = _DUR.fullmatch(dur).groups()
        t0 = int(dt.datetime.fromisoformat(start).timestamp())
        for k in range(int(d or 0) * 24 + int(h or 0)):
            out[t0 + 3600 * k] = v["value"] * factor
    return out

def wind_forecast(lat, lon):
    """dict(updated, hours=[[unix t, speed kt, gust kt, direction from (deg)], ...]) hourly from the
    current hour on, or None (with a note) if the weather service can't be reached."""
    try:
        url = _grid_url(round(lat, 4), round(lon, 4))
        p = _grid(url, int(time.time() // 3600))
    except Exception as e:
        print("  wind unavailable:", e, flush=True)
        return None
    sp, gu, di = _hourly(p["windSpeed"], KMH_TO_KT), _hourly(p["windGust"], KMH_TO_KT), _hourly(p["windDirection"])
    now = int(time.time() // 3600 * 3600)
    hours = [[t, round(sp[t], 1), round(gu.get(t, sp[t]), 1), round(di[t])]
             for t in sorted(sp) if t >= now and t in di]
    return dict(source="NOAA National Weather Service", grid=url.rsplit("/", 2)[-2:], updated=p["updateTime"],
                hours=hours)

# ---------- tide ----------

@functools.lru_cache(maxsize=None)
def _tide_events(station, day):                      # `day`: cache key (predictions don't change)
    start = dt.datetime.fromisoformat(day) - dt.timedelta(days=1)
    d = _get("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
             dict(product="predictions", application="surfmodel", begin_date=start.strftime("%Y%m%d"),
                  range=24 * 10, datum="MLLW", station=station, time_zone="gmt", units="english",
                  interval="hilo", format="json"), headers={"User-Agent": UA["User-Agent"]})
    if "predictions" not in d:
        raise RuntimeError(d.get("error", {}).get("message", "no predictions"))
    return tuple((int(dt.datetime.strptime(p["t"], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp()),
                  round(float(p["v"]), 2), p["type"]) for p in d["predictions"])

def tide_at(events, t):
    """Tide height (ft above MLLW) at unix time(s) `t`: half-cosine between the surrounding high and low."""
    te = np.array([e[0] for e in events], float); he = np.array([e[1] for e in events], float)
    t = np.atleast_1d(np.asarray(t, float))
    j = np.clip(np.searchsorted(te, t) - 1, 0, len(te) - 2)
    f = np.clip((t - te[j]) / (te[j + 1] - te[j]), 0, 1)
    return he[j] + (he[j + 1] - he[j]) * (1 - np.cos(np.pi * f)) / 2

def tide_predictions(station):
    """dict(station, events=[[unix t, ft, "H"|"L"]]) from a day ago to ~9 days ahead, or None."""
    if not station:
        return None
    try:
        ev = _tide_events(station, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"))
    except Exception as e:
        print("  tide unavailable:", e, flush=True)
        return None
    return dict(source="NOAA CO-OPS tide predictions", station=station, datum="MLLW",
                events=[list(e) for e in ev])

if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else "steamer-lane"
    s = next(s for s in config.load_spots(kind="spot") if s["slug"] == slug)
    w = wind_forecast(s["lat"], s["lon"])
    print(f"{s['name']}: wind {w['grid']}, updated {w['updated']}")
    for h in w["hours"][:12]:
        print(f"  {dt.datetime.fromtimestamp(h[0], dt.timezone.utc):%a %H:%M}Z  {h[1]:4.1f} kt (gust {h[2]:.0f}) from {h[3]}°")
    T = tide_predictions(s.get("tide"))
    now = time.time()
    print(f"tide at station {s.get('tide')}: {float(tide_at(T['events'], now)[0]):.1f} ft now")
    for e in [e for e in T["events"] if e[0] > now][:4]:
        print(f"  {'high' if e[2] == 'H' else 'low '} {e[1]:4.1f} ft at {dt.datetime.fromtimestamp(e[0], dt.timezone.utc):%a %H:%M}Z")
