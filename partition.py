"""Split a directional wave spectrum S(f, θ) into separate swell systems ("partitions").

Uses steepest-ascent (watershed) partitioning, the standard approach in wave models:
every spectral bin is assigned to the peak it climbs to. Partitions with little energy
are merged into the neighbouring partition they touch most.
"""
import numpy as np
from scipy.ndimage import gaussian_filter

def partition(S, f, dirs, df, dth, min_frac=0.04, max_parts=5):
    """S: (nf, nd) energy density [m²/Hz/rad] on 'from' directions `dirs` (deg, evenly spaced).
    Returns a list of dicts sorted by energy: mask, hs, tp, dp (deg), frac."""
    nf, nd = S.shape
    Ss = gaussian_filter(S, sigma=(1.0, 1.5), mode=("nearest", "wrap"))
    # steepest-ascent pointer for each bin over its 3x3 neighbourhood (direction wraps)
    best = np.arange(nf * nd).reshape(nf, nd)
    bestv = Ss.copy()
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == dj == 0:
                continue
            fi = np.clip(np.arange(nf) + di, 0, nf - 1)
            nb = Ss[fi][:, (np.arange(nd) + dj) % nd]
            idx = (fi[:, None] * nd + (np.arange(nd)[None, :] + dj) % nd)
            up = nb > bestv
            bestv = np.where(up, nb, bestv); best = np.where(up, idx, best)
    ptr = best.ravel()
    for _ in range(nf + nd):                                  # pointer jumping to the peak
        ptr = ptr[ptr]
    lab = np.unique(ptr, return_inverse=True)[1].reshape(nf, nd)

    E = S * df[:, None] * dth                                 # m² per bin
    total = E.sum()
    # merge small partitions into the neighbour they share the longest border with
    while True:
        ids = np.unique(lab)
        en = np.array([E[lab == i].sum() for i in ids])
        small = [(e, i) for i, e in zip(ids, en) if e < min_frac * total]
        if (not small and len(ids) <= max_parts) or len(ids) == 1:
            break
        i = min(small)[1] if small else ids[en.argmin()]
        m = lab == i
        nb = np.concatenate([lab[np.roll(m, s, a)] for s, a in ((1, 0), (-1, 0), (1, 1), (-1, 1))])
        nb = nb[nb != i]
        if nb.size == 0:
            break
        vals, cnt = np.unique(nb, return_counts=True)
        lab[m] = vals[cnt.argmax()]

    parts = []
    th = np.radians(dirs)
    for i in np.unique(lab):
        m = lab == i
        Em = np.where(m, E, 0.0)
        e1 = Em.sum(1)
        a = np.arctan2((Em * np.sin(th)).sum(), (Em * np.cos(th)).sum())
        parts.append(dict(mask=m, hs=4 * np.sqrt(Em.sum()), tp=1 / f[e1.argmax()],
                          dp=np.degrees(a) % 360, frac=Em.sum() / total))
    return sorted(parts, key=lambda p: -p["hs"])

def compass(d):
    return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW",
            "W", "WNW", "NW", "NNW"][int((d % 360) / 22.5 + 0.5) % 16]

def label(p):
    kind = "groundswell" if p["tp"] >= 13 else "swell" if p["tp"] >= 9 else "wind swell"
    return f"{p['tp']:.0f}s {compass(p['dp'])} {kind} ({p['dp']:.0f}°)"
