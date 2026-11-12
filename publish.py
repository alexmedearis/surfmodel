"""Publish each spot's data as files: what the website (and later a mobile app) reads.

  python publish.py [slug ...]                  all spots, or these
  python publish.py --only now,lineup           just these products (map, now, lineup, forecast)
  python publish.py --at "2026-11-09 18:00"     from the buoy reading nearest a UTC time
  python publish.py --store local:/some/dir     where to write (default: $SURF_STORE, else local:out/data)

Layout under the store root (versioned, so old app versions keep working when the format changes):
  v1/spots/index.json                  the spots: slug, name, region, position, break type
  v1/spots/conditions.json             every spot's current surf height and key facts (for the spot list)
  v1/spots/<slug>/map.json             coastline, depth, map views              (once per spot)
  v1/spots/<slug>/now.json             current swells, paths, surf height       (each buoy reading)
  v1/spots/<slug>/lineup.json + .bin   "In the water" wave field: JSON header + raw grids
  v1/spots/<slug>/forecast.json        7-day forecast                           (each forecast run)
  v1/spots/<slug>/weather.json         wind, tide and surf rating, hourly for 7 days (every hour)

Every JSON file carries schema_version and generated_at. The lineup grids are in lineup.bin; in
lineup.json each one is {"bin": {"offset", "length", "dtype"}} pointing into it (little-endian).

Storage is behind a small interface (put/get) so the same code writes to a local folder now and
to Google Cloud Storage when deployed; pick it with --store or the SURF_STORE setting.
"""
import datetime as dt, json, os, sys
import numpy as np
import config
from common import Bathy
from inputs import region_inputs
from predict import load_tables
from products.spot_map import spot_map
from products.spot_now import spot_now
from products.spot_lineup import spot_lineup
from products.spot_forecast import spot_forecast
from products.spot_weather import spot_weather
from products.insights import conditions, wind_state, tide_state, rating
import weather as W
from products.geometry import Frame, shore_normal

API = "v1"
PRODUCTS = ("map", "now", "lineup", "forecast", "weather")
CACHE_SECONDS = dict(map=86400, now=300, lineup=300, forecast=900, weather=300, index=300, conditions=300)   # for the CDN, later

# ---------- storage ----------

class LocalStore:
    """A folder on disk. Writes are atomic (temp file + rename), so a reader never sees half a file."""
    def __init__(self, root):
        self.root = os.path.abspath(root)
    def put(self, path, data, content_type="application/json", cache_seconds=300):
        full = os.path.join(self.root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        tmp = full + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, full)
    def get(self, path):
        with open(os.path.join(self.root, path), "rb") as fh:
            return fh.read()
    def __str__(self):
        return self.root

class CloudStore:
    """A Cloud Storage bucket: gs://bucket or gs://bucket/prefix (the Firebase Storage bucket when
    deployed). Credentials come from the environment: the job's service account on Cloud Run,
    `gcloud auth application-default login` on a laptop. With STORAGE_EMULATOR_HOST set (e.g.
    http://127.0.0.1:9199) it writes to the local Firebase Storage emulator instead.
    Each upload replaces the whole object at once, so readers never see half a file."""
    def __init__(self, url):
        from google.cloud import storage                 # only needed when publishing to the cloud
        bucket, _, prefix = url[len("gs://"):].partition("/")
        self.url, self.prefix = url.rstrip("/"), prefix.strip("/")
        emulator = os.environ.get("STORAGE_EMULATOR_HOST")
        if emulator:
            from google.auth.credentials import AnonymousCredentials
            client = storage.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT", "demo-surf"),
                                    credentials=AnonymousCredentials(), client_options={"api_endpoint": emulator})
        else:
            client = storage.Client()
        self.bucket = client.bucket(bucket)
    def _key(self, path):
        return f"{self.prefix}/{path}" if self.prefix else path
    def put(self, path, data, content_type="application/json", cache_seconds=300):
        blob = self.bucket.blob(self._key(path))
        blob.cache_control = f"public, max-age={cache_seconds}"
        blob.upload_from_string(data, content_type=content_type)
    def get(self, path):
        from google.api_core.exceptions import NotFound
        try:
            return self.bucket.blob(self._key(path)).download_as_bytes()
        except NotFound:
            raise FileNotFoundError(path)
    def __str__(self):
        return self.url

def get_store(spec=None):
    spec = spec or os.environ.get("SURF_STORE") or "local:" + os.path.join(config.OUT, "data")
    if spec.startswith("gs://"):
        return CloudStore(spec)
    return LocalStore(spec[len("local:"):] if spec.startswith("local:") else spec)

# ---------- encoding ----------

def _now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _json(d):
    return json.dumps(dict(d, generated_at=_now_iso()), separators=(",", ":")).encode()

_DTYPES = {np.dtype(np.uint8): "uint8", np.dtype("<u2"): "uint16le"}

def pack_binary(d):
    """Move every numpy array in `d` into one buffer. Returns (header with {"bin": ...}
    descriptors in place of the arrays, bytes)."""
    buf = bytearray()
    def walk(v):
        if isinstance(v, np.ndarray):
            if len(buf) % 2:
                buf.append(0)                        # keep 16-bit grids aligned
            b = np.ascontiguousarray(v).tobytes()
            desc = dict(offset=len(buf), length=int(v.size), dtype=_DTYPES[v.dtype])
            buf.extend(b)
            return {"bin": desc}
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    return walk(d), bytes(buf)

def unpack_binary(header, buf):
    """Inverse of pack_binary: put the arrays back (as numpy)."""
    dt_ = {"uint8": np.uint8, "uint16le": np.dtype("<u2")}
    def walk(v):
        if isinstance(v, dict) and set(v) == {"bin"}:
            b = v["bin"]; t = np.dtype(dt_[b["dtype"]])
            return np.frombuffer(buf, t, count=b["length"], offset=b["offset"])
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list):
            return [walk(x) for x in v]
        return v
    return walk(header)

# ---------- publishing ----------

def spot_path(slug, name):
    return f"{API}/spots/{slug}/{name}"

def publish_spot(store, tab, I, only=PRODUCTS):
    """Compute and write the chosen products for one spot. Returns {product: bytes written}."""
    fine = Bathy.fine(tab["slug"])
    sizes = {}
    def put(name, data, ctype="application/json", key=None):
        store.put(spot_path(tab["slug"], name), data, ctype, CACHE_SECONDS[key or name.split(".")[0]])
        sizes[name] = len(data)
    if "map" in only:
        put("map.json", _json(spot_map(tab, I["coarse"], fine)))
    fc = None
    if "forecast" in only and I["fc"]:               # keep the last forecast if NOAA is unreachable
        fc = spot_forecast(tab, I["fc"])
        put("forecast.json", _json(fc))
    # wind and tide: only for the latest reading (a replay of a past time would get today's)
    wind = tide = None
    if I.get("live", True) and ("now" in only or "weather" in only):
        wind = W.wind_forecast(tab["lat"], tab["lon"])
        tide = W.tide_predictions(config.tide_station(tab["slug"]))
    sn = round(shore_normal(fine, Frame(tab["lat"], tab["lon"])))
    now = lu = None
    if "now" in only or "lineup" in only:
        now = spot_now(tab, I["spec"], I["parts"], I["coarse"], fine)
        now["buoy_time"] = I["spec"]["time"].strftime("%Y-%m-%dT%H:%M:%SZ")
    if "lineup" in only:
        lu = spot_lineup(tab, I["coarse"], fine, now["swells"])
        if lu is None:                               # nothing reaching the spot: say so, don't leave an old field
            put("lineup.json", _json(dict(schema_version=now["schema_version"], slug=tab["slug"], swells=[])))
        else:
            header, blob = pack_binary(lu)
            put("lineup.bin", blob, "application/octet-stream", "lineup")
            put("lineup.json", _json(dict(header, bin_file="lineup.bin", bin_bytes=len(blob))))
    if "now" in only:
        ins = conditions(now, lu, sn)
        t = I["spec"]["time"].timestamp()
        w = None
        if wind and wind["hours"]:
            h = min(wind["hours"], key=lambda h: abs(h[0] + 1800 - t))
            ins["wind"] = w = wind_state(h[1], h[2], h[3], sn)
        if tide:
            ins["tide"] = tide_state(tide["events"], t, W.tide_at)
        tp = (ins.get("main_swell") or {}).get("period") or 8
        ins["rating"] = dict(rating(now["breakers"][0], now["breakers"][1], tp, w), wind_known=w is not None)
        now["insights"] = ins
        put("now.json", _json(now))
    if "weather" in only and (wind or tide):
        if fc is None:
            try:
                fc = json.loads(store.get(spot_path(tab["slug"], "forecast.json")))
            except FileNotFoundError:
                pass
        put("weather.json", _json(spot_weather(tab, wind, tide, sn, fc)))
    return sizes

def publish_index(store):
    spots = []
    for s in config.load_spots(kind="spot"):
        if os.path.exists(config.table_path(s["slug"])):
            spots.append(dict(slug=s["slug"], name=s["name"], region=s["region"],
                              region_name=config.REGIONS[s["region"]]["name"], lat=s["lat"], lon=s["lon"],
                              break_type=config.break_type(s["slug"])))
    store.put(f"{API}/spots/index.json", _json(dict(schema_version=1, spots=spots)),
              cache_seconds=CACHE_SECONDS["index"])
    return len(spots)

def publish_conditions(store, slugs=None):
    """conditions.json: each spot's surf height and key facts from its published now.json, so the
    spot list needs one small file instead of every spot's data. Includes the forecast as
    [unix time, low, high] surf height, for the list's 7-day mini chart. Returns how many spots."""
    rows = []
    for s in config.load_spots(kind="spot"):
        try:
            n = json.loads(store.get(spot_path(s["slug"], "now.json")))
        except FileNotFoundError:
            continue
        ins = n.get("insights") or {}
        main = ins.get("main_swell") or {}
        peel = ins.get("peel") or {}
        try:
            fc = json.loads(store.get(spot_path(s["slug"], "forecast.json")))
            fc = [[h["t"], round(h["lo"]), round(h["hi"])] for h in fc["hours"]]
        except FileNotFoundError:
            fc = []
        try:
            wx = json.loads(store.get(spot_path(s["slug"], "weather.json")))
            rt = [r for r in wx["rating"] if r[0] % 10800 == 0]          # every 3 hours is plenty for the list
        except FileNotFoundError:
            rt = []
        w, td = ins.get("wind") or {}, ins.get("tide") or {}
        rows.append(dict(slug=s["slug"], rating=ins.get("rating"), wind=dict(kt=w["kt"], rel=w["rel"], dir=w["dir"]) if w else None,
                         tide=dict(ft=td["ft"], rising=td["rising"]) if td else None, ratings=rt,
                         surf_ft=n["breakers"], hs_ft=n["hs_ft"], main=main.get("short"),
                         period=main.get("period"), dir=main.get("dir"), favors=ins.get("favors"), mix=ins.get("mix"),
                         peel=dict(side=peel["side"], cls=peel["cls"]) if peel.get("cls") else None,
                         buoy_time=n.get("buoy_time"), updated=n.get("generated_at"), forecast=fc))
    store.put(f"{API}/spots/conditions.json", _json(dict(schema_version=1, spots=rows)),
              cache_seconds=CACHE_SECONDS["conditions"])
    return len(rows)

# ---------- reading back (what the website does in JavaScript; used by tests and the backend) ----------

def load_spot(store, slug):
    """dict(map, now, forecast, lineup) as published (lineup grids as numpy arrays; missing -> None)."""
    def get_json(name):
        try:
            return json.loads(store.get(spot_path(slug, name)))
        except FileNotFoundError:
            return None
    out = {k: get_json(f"{k}.json") for k in ("map", "now", "forecast", "weather")}
    lu = get_json("lineup.json")
    if lu and lu.get("swells"):
        lu = unpack_binary(lu, store.get(spot_path(slug, lu["bin_file"])))
    out["lineup"] = lu if lu and lu.get("swells") else None
    return out

def publish(store, only=PRODUCTS, slugs=None, when=None):
    """Publish `only` for the given spots (default all), then the index and conditions files.
    A spot that fails is reported and skipped, so one bad spot doesn't stop the rest.
    Returns the slugs that failed."""
    spots = [s for s in config.load_spots(kind="spot") if not slugs or s["slug"] in slugs]
    print(f"publishing {', '.join(only)} to {store}", flush=True)
    failed = []
    for region in dict.fromkeys(s["region"] for s in spots):
        tabs = [t for t in load_tables(region) if t["slug"] in {s["slug"] for s in spots}]
        if not tabs:
            continue
        try:
            I = region_inputs(region, when, with_forecast="forecast" in only)
        except Exception as e:                       # e.g. the buoy feed is down
            print(f"  {region}: couldn't get the inputs: {e!r}", flush=True)
            failed += [t["slug"] for t in tabs]
            continue
        for tab in tabs:
            print(tab["name"], flush=True)
            try:
                sizes = publish_spot(store, tab, I, only)
                print("  wrote " + ", ".join(f"{k} {v / 1e3:.0f} KB" for k, v in sizes.items()), flush=True)
            except Exception as e:
                print(f"  FAILED: {e!r}", flush=True)
                failed.append(tab["slug"])
    print(f"index: {publish_index(store)} spots", flush=True)
    if {"now", "forecast", "weather"} & set(only):
        print(f"conditions: {publish_conditions(store)} spots", flush=True)
    return failed

if __name__ == "__main__":
    args = sys.argv[1:]
    when, store_spec, only = None, None, PRODUCTS
    if "--at" in args:
        i = args.index("--at"); when = dt.datetime.fromisoformat(args[i + 1]).replace(tzinfo=dt.timezone.utc); del args[i:i + 2]
    if "--store" in args:
        i = args.index("--store"); store_spec = args[i + 1]; del args[i:i + 2]
    if "--only" in args:
        i = args.index("--only"); only = tuple(args[i + 1].split(",")); del args[i:i + 2]
        bad = set(only) - set(PRODUCTS)
        if bad:
            sys.exit(f"unknown product(s) {', '.join(bad)}: choose from {', '.join(PRODUCTS)}")
    failed = publish(get_store(store_spec), only, [a for a in args if not a.startswith("--")], when)
    if failed:
        sys.exit(f"failed: {', '.join(failed)}")
