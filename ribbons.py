"""Build the spot pages: out/ribbons_<slug>.html (open in a browser).

  python ribbons.py [slug ...]                  all spots, or these
  python ribbons.py --at "2026-11-07 06:00"     replay the buoy reading nearest that UTC time
  python ribbons.py --hours-ago 24 linda-mar    or one about that long ago
  python ribbons.py --no-forecast               skip the 7-day forecast (always skipped with --at)
  python ribbons.py --no-lineup                 skip the "In the water" wave field (faster)

Everything on the page is computed by the products/ package (map, current swells, lineup,
forecast); this script fetches the inputs, calls them, and pastes the result into
ribbons_template.html. See products/geometry.py for how the swell paths are built.
"""
import json, os, sys, datetime as dt
import config
from common import Bathy
from inputs import region_inputs
from predict import load_tables
from products.spot_map import spot_map
from products.spot_now import spot_now
from products.spot_lineup import spot_lineup
from products.spot_forecast import spot_forecast
from products.page import page_data

def build(tab, spec, parts, coarse, fc=None, with_lineup=True):
    """Everything the page shows for one spot, as one dict (the page's DATA)."""
    fine = Bathy.fine(tab["slug"])
    now = spot_now(tab, spec, parts, coarse, fine)
    lu = spot_lineup(tab, coarse, fine, now["swells"]) if with_lineup else None
    return page_data(spot_map(tab, coarse, fine), now, spot_forecast(tab, fc) if fc else None, lu)

if __name__ == "__main__":
    args = sys.argv[1:]
    when = None
    if "--at" in args:                                 # e.g. --at "2026-11-07 06:00" (UTC)
        i = args.index("--at"); when = dt.datetime.fromisoformat(args[i + 1]).replace(tzinfo=dt.timezone.utc); del args[i:i + 2]
    if "--hours-ago" in args:                          # e.g. --hours-ago 24 to replay yesterday
        i = args.index("--hours-ago")
        when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=float(args[i + 1])); del args[i:i + 2]
    slugs = [a for a in args if not a.startswith("--")]
    spots = [s for s in config.load_spots(kind="spot") if not slugs or s["slug"] in slugs]
    tpl = open(os.path.join(config.HERE, "ribbons_template.html")).read()
    for region in dict.fromkeys(s["region"] for s in spots):
        tabs = [t for t in load_tables(region) if t["slug"] in {s["slug"] for s in spots}]
        if not tabs:
            continue
        I = region_inputs(region, when, with_forecast="--no-forecast" not in sys.argv)
        for tab in tabs:
            print(tab["name"], flush=True)
            data = build(tab, I["spec"], I["parts"], I["coarse"], I["fc"], with_lineup="--no-lineup" not in sys.argv)
            out = os.path.join(config.OUT, f"ribbons_{tab['slug']}.html")
            open(out, "w").write(tpl.replace("/*DATA*/null", json.dumps(data, separators=(",", ":"))))
            print("  saved", os.path.relpath(out, config.HERE))
