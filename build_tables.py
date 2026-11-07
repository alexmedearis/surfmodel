import json, numpy as np, time
from common import Bathy, SPOTS
from raytrace import transfer_table, PERIODS, DIR_BINS
b = Bathy()
tables = {}
for name, (la, lo) in SPOTS.items():
    t = time.time()
    sla, slo, sh = b.site_point(la, lo)
    W = transfer_table(b, sla, slo, sh)
    tables[name] = dict(lat=float(sla), lon=float(slo), depth=float(sh), W=W.tolist())
    print(f"{name}: {time.time()-t:.0f}s")
    for T, row in zip(PERIODS, W):
        if T in (8, 12, 16, 20):
            show = {d: row[int(d / 5)] for d in (180, 200, 220, 240, 260, 280, 300, 320)}
            print(f"  T={T:2d}s  " + "  ".join(f"{d}°:{v:4.2f}" for d, v in show.items()))
json.dump(dict(periods=PERIODS, dir_bins=DIR_BINS.tolist(), spots=tables), open("data/transfer_tables.json", "w"))
