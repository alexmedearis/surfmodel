"""Nowcast surf at each spot: live Point Reyes buoy spectrum x per-spot transfer table."""
import json, sys, numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from common import c_cg
from buoy import latest, mem

M2FT = 3.281
TBL = json.load(open("data/transfer_tables.json"))
PER, DIRS = np.array(TBL["periods"], float), np.array(TBL["dir_bins"])

def W_at(Wtab, T):
    """Transfer row for period T (linear in frequency between table periods, clamped)."""
    fq, f = 1 / PER, 1 / np.clip(T, PER.min(), PER.max())
    j = np.clip(np.searchsorted(-fq, -f), 1, len(PER) - 1)     # fq is decreasing
    w = (fq[j - 1] - f) / (fq[j - 1] - fq[j])
    return (1 - w) * Wtab[j - 1] + w * Wtab[j]

def breaking_height(hs_site, T, h_site):
    """Rough breaker height: back out an equivalent deep-water height, then Komar & Gaudiano (1975)."""
    c, cg = c_cg(T, h_site); ks = np.sqrt((9.81 * T / 4 / np.pi) / cg)
    h0 = hs_site / ks
    return 0.39 * 9.81 ** 0.2 * (T * h0 ** 2) ** 0.4

def predict(spec, spot):
    sp = TBL["spots"][spot]; Wtab = np.array(sp["W"])
    D = mem(spec["a1"], spec["b1"], spec["a2"], spec["b2"], DIRS)        # (nf, ndir) per rad
    S_off = spec["E"][:, None] * D                                       # m²/Hz/rad
    dth = np.radians(5.0)
    T = 1 / spec["f"]
    Wf = np.array([W_at(Wtab, t) for t in T])
    E_site = (Wf * S_off).sum(1) * dth                                   # m²/Hz
    swell = T >= 9
    hs = 4 * np.sqrt((E_site * spec["df"]).sum())
    hs_swell = 4 * np.sqrt((E_site[swell] * spec["df"][swell]).sum())
    tp = T[E_site.argmax()]
    return dict(spot=spot, hs=hs, hs_swell=hs_swell, tp=tp, hb=breaking_height(hs, tp, sp["depth"]),
                E_site=E_site, S_off=S_off)

def report(spec):
    print(f"Point Reyes buoy (CDIP 029) @ {spec['time']:%Y-%m-%d %H:%M} UTC: "
          f"Hs {spec['hs']:.1f} m ({spec['hs']*M2FT:.0f} ft), Tp {spec['tp']:.0f}s, from {spec['dp']:.0f}°\n")
    print(f"{'spot':12s} {'Hs@10m':>8s} {'swell':>7s} {'Tp':>5s} {'est. breakers':>14s}")
    res = []
    for spot in TBL["spots"]:
        r = predict(spec, spot); res.append(r)
        print(f"{spot:12s} {r['hs']*M2FT:6.1f}ft {r['hs_swell']*M2FT:5.1f}ft {r['tp']:4.0f}s"
              f"   ~{r['hb']*M2FT*0.8:.0f}-{r['hb']*M2FT*1.2:.0f} ft")
    return res

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
    spec = latest()
    report(spec)
    print("\nWhat-if: same 2 m (6.6 ft) deep-water swell from different directions -> est. breakers (ft)")
    scen = [(14, 300, "14s NW 300°"), (14, 270, "14s W 270°"), (16, 220, "16s SW 220°"), (17, 195, "17s S 195°")]
    print(f"{'':12s}" + "".join(f"{s[2]:>14s}" for s in scen))
    for spot in TBL["spots"]:
        row = [predict(synthetic(2.0, tp, d), spot)["hb"] * M2FT for tp, d, _ in scen]
        print(f"{spot:12s}" + "".join(f"{v:14.1f}" for v in row))
