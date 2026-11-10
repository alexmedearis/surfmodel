"""The "In the water" wave field (lineup.py) for the swells reaching a spot: crest phase, height,
breaking threshold and set arrival time on a grid around the break, plus break lines and peel.

The grids are packed small (8- and 16-bit numpy arrays). The page gets them base64-encoded
(page.py); published, they go in a binary file next to a small JSON header (publish.py)."""
import numpy as np
import config, lineup as LU
from predict import M2FT
from . import SCHEMA_VERSION

def _pack(a, dtype):
    return np.ascontiguousarray(a, dtype=dtype)

def spot_lineup(tab, coarse, fine, swells):
    """`swells`: the swells list from spot_now (their strands say which directions get in)."""
    live = [s for s in swells if not s["blocked"] and s["strands"] and s["site_ft"] >= 0.5][:3]
    if not live:
        return None
    out, h = [], None
    for s in live:
        # centre the spread on the directions that actually get in
        w = np.array([t["share"] for t in s["strands"]]); a = np.radians([t["frm"] for t in s["strands"]])
        frm = float(np.degrees(np.arctan2((w * np.sin(a)).sum(), (w * np.cos(a)).sum())) % 360)
        F = LU.wavefield(coarse, fine, tab["lat"], tab["lon"], max(s["tp"], 5), frm)
        if F is None:
            continue
        nc = F["nc"]; c = nc // 2
        # match the height at the model point to the transfer table's (which has the full spectrum)
        Kc = np.nanmean(F["K"][c - 5:c + 6, c - 5:c + 6])
        f = float(np.clip((s["site_ft"] / max(s["off_ft"], 0.1)) / max(Kc, 1e-3), 0.6, 1.6)) if Kc > 0 else 1.0
        K, bth = F["K"] * f, F["bth"] / f
        H0 = s["off_ft"] / M2FT
        pl = LU.peel(dict(F, bth=bth), H0)
        tg = F["tg"]; tg0 = np.nanmin(tg) if np.isfinite(tg).any() else 0
        out.append(dict(i=swells.index(s), T=round(float(F["T"]), 2), H0=round(H0, 2), frm=round(frm),
                        ph=_pack(np.round((F["phase"] % (2 * np.pi)) / (2 * np.pi) * 256) % 256, np.uint8),
                        K=_pack(np.clip(np.nan_to_num(K) * 100, 0, 255).round(), np.uint8),
                        bth=_pack(np.where(np.isfinite(bth), np.clip(bth * 20, 0, 254), 255).round(), np.uint8),
                        tg=_pack(np.clip(np.nan_to_num(tg - tg0, nan=0) * 10, 0, 65535).round(), "<u2"),
                        peel=[dict(x=np.round(g["x"][::2], 1).tolist(), y=np.round(g["y"][::2], 1).tolist(),
                                   angle=round(float(np.median(g["angle"])), 0), right=g["right"],
                                   dir=[round(float(np.mean(g["vx"])), 3), round(float(np.mean(g["vy"])), 3)],
                                   len=round(float(np.hypot(np.diff(g["x"]), np.diff(g["y"])).sum())))
                              for g in pl]))
        h = F["h"]
    if not out:
        return None
    spot = next(r for r in config.load_spots() if r["slug"] == tab["slug"])
    sx, sy = fine.to_xy(spot["lat"], spot["lon"])
    return dict(schema_version=SCHEMA_VERSION, slug=tab["slug"],
                nc=nc, cell=LU.CELL_M, depth=_pack(np.clip(h * 8, 0, 255).round(), np.uint8), swells=out,
                spot=[round(float(sx) - F["x0"], 1), round(float(sy) - F["y0"], 1)], break_type=spot.get("break") or "")
