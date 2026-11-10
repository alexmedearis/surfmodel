"""Publish each spot's data as files: what the website (and later a mobile app) reads.

  python publish.py [slug ...]                  all spots, or these
  python publish.py --only now,lineup           just these products (map, now, lineup, forecast)
  python publish.py --at "2026-11-09 18:00"     from the buoy reading nearest a UTC time
  python publish.py --store local:/some/dir     where to write (default: $SURF_STORE, else local:out/data)

Layout under the store root (versioned, so old app versions keep working when the format changes):
  v1/spots/index.json                  the spots: slug, name, region, position, break type
  v1/spots/<slug>/map.json             coastline, depth, map views              (once per spot)
  v1/spots/<slug>/now.json             current swells, paths, surf height       (each buoy reading)
  v1/spots/<slug>/lineup.json + .bin   "In the water" wave field: JSON header + raw grids
  v1/spots/<slug>/forecast.json        7-day forecast                           (each forecast run)

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

API = "v1"
PRODUCTS = ("map", "now", "lineup", "forecast")
CACHE_SECONDS = dict(map=86400, now=300, lineup=300, forecast=900, index=300)   # for the CDN, later

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
    """Google Cloud Storage bucket (gs://bucket/prefix). Comes with the deployment step."""
    def __init__(self, url):
        raise NotImplementedError("Cloud Storage publishing isn't set up yet; use a local store for now")

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
    now = None
    if "now" in only or "lineup" in only:
        now = spot_now(tab, I["spec"], I["parts"], I["coarse"], fine)
        now["buoy_time"] = I["spec"]["time"].strftime("%Y-%m-%dT%H:%M:%SZ")
        if "now" in only:
            put("now.json", _json(now))
    if "lineup" in only:
        lu = spot_lineup(tab, I["coarse"], fine, now["swells"])
        if lu is None:                               # nothing reaching the spot: say so, don't leave an old field
            put("lineup.json", _json(dict(schema_version=now["schema_version"], slug=tab["slug"], swells=[])))
        else:
            header, blob = pack_binary(lu)
            put("lineup.bin", blob, "application/octet-stream", "lineup")
            put("lineup.json", _json(dict(header, bin_file="lineup.bin", bin_bytes=len(blob))))
    if "forecast" in only and I["fc"]:               # keep the last forecast if NOAA is unreachable
        put("forecast.json", _json(spot_forecast(tab, I["fc"])))
    return sizes

def publish_index(store):
    spots = []
    for s in config.load_spots(kind="spot"):
        if os.path.exists(config.table_path(s["slug"])):
            spots.append(dict(slug=s["slug"], name=s["name"], region=s["region"],
                              region_name=config.REGIONS[s["region"]]["name"], lat=s["lat"], lon=s["lon"],
                              break_type=s.get("break") or ""))
    store.put(f"{API}/spots/index.json", _json(dict(schema_version=1, spots=spots)),
              cache_seconds=CACHE_SECONDS["index"])
    return len(spots)

# ---------- reading back (what the website does in JavaScript; used by tests and the backend) ----------

def load_spot(store, slug):
    """dict(map, now, forecast, lineup) as published (lineup grids as numpy arrays; missing -> None)."""
    def get_json(name):
        try:
            return json.loads(store.get(spot_path(slug, name)))
        except FileNotFoundError:
            return None
    out = {k: get_json(f"{k}.json") for k in ("map", "now", "forecast")}
    lu = get_json("lineup.json")
    if lu and lu.get("swells"):
        lu = unpack_binary(lu, store.get(spot_path(slug, lu["bin_file"])))
    out["lineup"] = lu if lu and lu.get("swells") else None
    return out

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
    store = get_store(store_spec)
    slugs = [a for a in args if not a.startswith("--")]
    spots = [s for s in config.load_spots(kind="spot") if not slugs or s["slug"] in slugs]
    print(f"publishing {', '.join(only)} to {store}")
    for region in dict.fromkeys(s["region"] for s in spots):
        tabs = [t for t in load_tables(region) if t["slug"] in {s["slug"] for s in spots}]
        if not tabs:
            continue
        I = region_inputs(region, when, with_forecast="forecast" in only)
        for tab in tabs:
            print(tab["name"], flush=True)
            sizes = publish_spot(store, tab, I, only)
            print("  wrote " + ", ".join(f"{k} {v / 1e3:.0f} KB" for k, v in sizes.items()), flush=True)
    print(f"index: {publish_index(store)} spots")
