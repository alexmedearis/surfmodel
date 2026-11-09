"""Ray-trace each spot into a transfer table (data/tables/<slug>.json).

  python build_tables.py                 all spots without a table yet
  python build_tables.py linda-mar ...   rebuild these
  python build_tables.py --all           rebuild everything
  add --coarse-only to skip the ~10 m nearshore grid (the original 90 m model)
  add --break-only to only (re)build each spot's breaking-zone table (surf height is computed there)

Spots run in parallel, one per CPU core.
"""
import json, os, sys, time, numpy as np
from multiprocessing import Pool
import config
from common import Bathy
from raytrace import transfer_table, PERIODS, DIR_BINS

def break_table(spot, coarse, fine):
    """Second table in the breaking zone (~BREAK_DEPTH deep, nearest the marked spot). Swell keeps
    bending between the ~10 m model point and where it breaks, a lot in sheltered corners
    (Princeton Jetty loses about half its height again), so surf height is computed here."""
    try:
        bla, blo, bh = fine.site_point(spot["lat"], spot["lon"], config.BREAK_DEPTH, radius_km=0.4)
    except ValueError:
        return {}
    Wb = transfer_table(coarse, bla, blo, bh, fine=fine)
    return dict(break_lat=float(bla), break_lon=float(blo), break_depth=float(bh), W_break=Wb.tolist())

def build(args):
    spot, coarse_only, break_only = args
    t = time.time()
    coarse = Bathy.coarse(spot["region"])
    use_fine = not coarse_only and os.path.exists(config.fine_path(spot["slug"]))
    fine = Bathy.fine(spot["slug"]) if use_fine else None
    if break_only:
        tab = json.load(open(config.table_path(spot["slug"])))
    else:
        sla, slo, sh = (fine or coarse).site_point(spot["lat"], spot["lon"], spot["depth"])
        W = transfer_table(coarse, sla, slo, sh, fine=fine)
        tab = dict(slug=spot["slug"], name=spot["name"], region=spot["region"], kind=spot["kind"],
                   station=spot["station"], lat=float(sla), lon=float(slo), depth=float(sh),
                   grid="fine" if use_fine else "coarse", periods=PERIODS, dir_bins=DIR_BINS.tolist(),
                   W=W.tolist())
    if spot["kind"] == "spot" and fine is not None:
        tab.update(break_table(spot, coarse, fine))
    os.makedirs(os.path.dirname(config.table_path(spot["slug"])), exist_ok=True)
    json.dump(tab, open(config.table_path(spot["slug"]), "w"))
    brk = f", breaking zone {tab['break_depth']:.1f} m deep" if "break_depth" in tab else ""
    return f"{spot['name']}: {tab['grid']} grid, model point {tab['depth']:.1f} m deep{brk}, {time.time() - t:.0f}s"

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    coarse_only = "--coarse-only" in sys.argv
    break_only = "--break-only" in sys.argv       # just add/redo the breaking-zone table
    spots = config.load_spots()
    if args:
        spots = [s for s in spots if s["slug"] in args]
    elif "--all" not in sys.argv:
        spots = [s for s in spots if not os.path.exists(config.table_path(s["slug"]))]
    with Pool(min(len(spots), os.cpu_count()) or 1) as pool:
        for msg in pool.imap_unordered(build, [(s, coarse_only, break_only) for s in spots]):
            print(msg, flush=True)
