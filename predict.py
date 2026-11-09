"""Nowcast surf at each spot: live deep-water buoy spectrum x per-spot transfer table,
broken down by swell system.

  python predict.py [region]            default: bayarea
  python predict.py [region] --what-if  also compare single clean swells from set directions
"""
import json, os, sys, numpy as np
import config
from common import c_cg
from buoy import latest, mem
from partition import partition, label

M2FT = 3.281
DTH = np.radians(5.0)

def load_tables(region=None, kind="spot"):
    tabs = []
    for s in config.load_spots(region, kind):
        p = config.table_path(s["slug"])
        if os.path.exists(p):
            t = json.load(open(p)); t["W"] = np.array(t["W"]); tabs.append(t)
    return tabs

def W_at(tab, T):
    """Transfer row for period T (linear in frequency between table periods, clamped)."""
    per = np.array(tab["periods"], float); Wtab = tab["W"]
    fq, f = 1 / per, 1 / np.clip(T, per.min(), per.max())
    j = np.clip(np.searchsorted(-fq, -f), 1, len(per) - 1)     # fq is decreasing
    w = (fq[j - 1] - f) / (fq[j - 1] - fq[j])
    return (1 - w) * Wtab[j - 1] + w * Wtab[j]

def offshore(spec, dirs):
    """Offshore S(f, θ) in m²/Hz/rad: from a forecast's full spectrum, or from a buoy's
    directional moments."""
    if "S2d" in spec:
        from forecast import on_dirs
        return on_dirs(spec, dirs)
    return spec["E"][:, None] * mem(spec["a1"], spec["b1"], spec["a2"], spec["b2"], dirs)

# Surf height, as shown everywhere: the face height of the waves breaking, from the typical bigger
# waves (the significant breaker height, average of the biggest third) up to the sets (about the
# biggest 10%, ~1.25x that for a Rayleigh height distribution). Not yet calibrated against observations.
SURF_RANGE = (1.0, 1.25)

_CAL = None
def calibration(slug):
    """Per-spot correction fitted from logged sessions (calibrate.py): dict(factor, n), or None."""
    global _CAL
    if _CAL is None:
        p = os.environ.get("SURF_CALIBRATION", os.path.join(config.DATA, "calibration.json"))
        _CAL = json.load(open(p)).get("spots", {}) if os.path.exists(p) else {}
    c = _CAL.get(slug)
    return c if c and c.get("factor", 1.0) != 1.0 else None

def surf_ft(hb, slug=None):
    """(low, high) surf height in feet from the significant breaker height in metres,
    with the spot's session calibration applied when it has one."""
    c = calibration(slug) if slug else None
    f = c["factor"] if c else 1.0
    return tuple(hb * M2FT * k * f for k in SURF_RANGE)

def breaking_height(hs_site, T, h_site):
    """Significant breaker height (m): back out an equivalent deep-water height, then
    Komar & Gaudiano (1975). Checked indirectly only: hs_site agrees with CDIP's MOP model
    to ~10% (check_mop.py), but nothing yet checks the breaking step itself."""
    c, cg = c_cg(T, h_site); ks = np.sqrt((9.81 * T / 4 / np.pi) / cg)
    h0 = hs_site / ks
    return 0.39 * 9.81 ** 0.2 * (T * h0 ** 2) ** 0.4

def predict(spec, tab, parts=None):
    dirs = np.array(tab["dir_bins"])
    S_off = offshore(spec, dirs)
    T = 1 / spec["f"]
    S_site = np.array([W_at(tab, t) for t in T]) * S_off
    E_site = S_site.sum(1) * DTH                                         # m²/Hz
    df = spec["df"]
    swell = T >= 9
    hs = 4 * np.sqrt((E_site * df).sum())
    tp = T[E_site.argmax()]
    comps = []
    for p in parts or []:
        e_off = (S_off * p["mask"] * df[:, None]).sum() * DTH
        e_site = (S_site * p["mask"] * df[:, None]).sum() * DTH
        comps.append(dict(label=label(p), hs_off=4 * np.sqrt(e_off), hs_site=4 * np.sqrt(e_site),
                          share=e_site / max((E_site * df).sum(), 1e-12)))
    return dict(slug=tab["slug"], name=tab["name"], hs=hs, hs_swell=4 * np.sqrt((E_site[swell] * df[swell]).sum()),
                tp=tp, hb=breaking_height(hs, tp, tab["depth"]), depth=tab["depth"],
                E_site=E_site, S_off=S_off, S_site=S_site, comps=comps)

def swells(spec, dirs=np.arange(0, 360, 5.0)):
    return partition(offshore(spec, dirs), spec["f"], dirs, spec["df"], DTH)

def report(spec, tabs):
    print(f"Input buoy {spec.get('stn', '')} @ {spec['time']:%Y-%m-%d %H:%M} UTC: "
          f"Hs {spec['hs']*M2FT:.1f} ft, Tp {spec['tp']:.0f}s, from {spec['dp']:.0f}°")
    parts = swells(spec)
    print("Swells offshore:")
    for p in parts:
        print(f"  {label(p):34s} {p['hs']*M2FT:5.1f} ft")
    res = []
    for tab in tabs:
        r = predict(spec, tab, parts); res.append(r)
        print(f"\n{r['name']}  (model point {r['depth']:.0f} m deep):  surf ~{surf_ft(r['hb'], r['slug'])[0]:.0f}-{surf_ft(r['hb'], r['slug'])[1]:.0f} ft"
              f"  (Hs {r['hs']*M2FT:.1f} ft, Tp {r['tp']:.0f}s)")
        for c in r["comps"]:
            pct = c["hs_site"] / max(c["hs_off"], 1e-9)
            print(f"  {c['label']:34s} {c['hs_off']*M2FT:5.1f} ft offshore -> {c['hs_site']*M2FT:5.1f} ft here"
                  f"  ({pct:4.0%} of height, {c['share']:4.0%} of energy here)")
    return res, parts

def synthetic(hs, tp, frm, spread=20.0):
    """A clean single swell, for 'what if' scenarios (JONSWAP-ish shape, cos^2s spread)."""
    f = np.linspace(0.04, 0.3, 64); df = np.gradient(f); fp = 1 / tp
    sig = np.where(f < fp, 0.07, 0.09)
    E = f ** -5 * np.exp(-1.25 * (fp / f) ** 4) * 3.3 ** np.exp(-((f - fp) ** 2) / (2 * sig**2 * fp**2))
    E *= (hs / 4) ** 2 / (E * df).sum()
    m = np.exp(-0.5 * (spread / 57.3) ** 2)                               # a1 magnitude for given spread
    a = np.radians(frm)
    return dict(time=None, hs=hs, tp=tp, dp=frm, f=f, df=df, E=E,
                a1=np.full(64, m * np.cos(a)), b1=np.full(64, m * np.sin(a)),
                a2=np.full(64, m**4 * np.cos(2 * a)), b2=np.full(64, m**4 * np.sin(2 * a)))

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    region = args[0] if args else "bayarea"
    tabs = load_tables(region)
    stn = config.REGIONS[region]["input_buoy"]
    spec = latest(stn); spec["stn"] = stn
    report(spec, tabs)
    if "--what-if" in sys.argv:
        print("\nWhat-if: same 2 m (6.6 ft) deep-water swell from different directions -> surf height, typical bigger waves (ft)")
        scen = [(14, 300, "14s NW 300°"), (14, 270, "14s W 270°"), (16, 220, "16s SW 220°"), (17, 195, "17s S 195°")]
        print(f"{'':14s}" + "".join(f"{s[2]:>14s}" for s in scen))
        for tab in tabs:
            row = [predict(synthetic(2.0, tp, d), tab)["hb"] * M2FT for tp, d, _ in scen]
            print(f"{tab['name']:14s}" + "".join(f"{v:14.1f}" for v in row))
