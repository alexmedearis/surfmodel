"""Regression check for the page data: build every spot from fixed inputs (a fixed buoy time
and a cached WaveWatch III run) and save or compare the result.

  python tests/snapshot.py save  <dir> [slug ...]   record (all spots, or add these to the recording)
  python tests/snapshot.py check <dir>     rebuild the recorded spots and compare exactly
  python tests/snapshot.py check-published <dir> <tmp>   same, but via the published data files

Used to make sure refactors don't change what the model publishes. The inputs still come from
the network (buoy archives) and data/forecast/, so the recording is only valid while those are.
"""
import json, os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from predict import load_tables

WHEN = dt.datetime(2026, 11, 9, 18, 0, tzinfo=dt.timezone.utc)
RUN = ("20261109", "12")

def build_all(published_to=None, slugs=None):
    """Page data for every spot from the fixed inputs. With `published_to` (a folder), go the
    long way: publish the data files there, read them back, and assemble the page from those,
    which checks the whole publish/read path too."""
    import ribbons, publish
    from products.page import page_data
    from inputs import region_inputs
    store = publish.LocalStore(published_to) if published_to else None
    out = {}
    for region in ("bayarea", "santacruz"):
        I = region_inputs(region, WHEN, run=RUN)
        for tab in load_tables(region):
            if slugs is not None and tab["slug"] not in slugs:
                continue
            print(tab["name"], flush=True)
            if store:
                publish.publish_spot(store, tab, I)
                P = publish.load_spot(store, tab["slug"])
                data = page_data(P["map"], P["now"], P["forecast"], P["lineup"])
            else:
                data = ribbons.build(tab, I["spec"], I["parts"], I["coarse"], I["fc"])
            out[tab["slug"]] = json.loads(json.dumps(data, separators=(",", ":")))
    return out

def diff(a, b, path=""):
    if type(a) != type(b):
        return [f"{path}: type {type(a).__name__} != {type(b).__name__}"]
    if isinstance(a, dict):
        out = [f"{path}.{k}: only in {'old' if k in a else 'new'}" for k in set(a) ^ set(b)]
        for k in set(a) & set(b):
            out += diff(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
            if len(out) > 20:
                break
        return out
    return [] if a == b else [f"{path}: {str(a)[:60]} != {str(b)[:60]}"]

if __name__ == "__main__":
    mode, d = sys.argv[1], sys.argv[2]
    if mode == "save":
        slugs = set(sys.argv[3:]) or None
        data = build_all(None, slugs)
        os.makedirs(d, exist_ok=True)
        for slug, v in data.items():
            json.dump(v, open(os.path.join(d, f"{slug}.json"), "w"), separators=(",", ":"))
        print(f"saved {len(data)} spots to {d}")
    else:
        recorded = {f[:-5] for f in os.listdir(d) if f.endswith(".json")}
        data = build_all(sys.argv[3] if mode == "check-published" else None, recorded)
        bad = 0
        for slug, v in data.items():
            ref = json.load(open(os.path.join(d, f"{slug}.json")))
            dd = diff(ref, v)
            print(f"{slug:16s} {'identical' if not dd else f'{len(dd)} differences'}")
            for line in dd[:10]:
                print("   ", line)
            bad += bool(dd)
        missing = recorded - set(data)
        if missing:
            print("recorded but no longer built:", ", ".join(sorted(missing)))
        sys.exit(1 if bad or missing else 0)
